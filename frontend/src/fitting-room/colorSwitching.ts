/**
 * Color switching (Part 46) -- client for POST /api/fitting-room/switch-color.
 *
 * Selecting a color never changes an existing image. The backend resolves the
 * color to a REAL retailer product through ShoppingAgent/MCP; this module
 * returns exactly that product, or a "not_found" result. Nothing is invented
 * and the slot's current product is left alone on anything but "replaced".
 */

import { categoryForSlot, slotForCategory, type OutfitSlot } from "./categoryMap";
import { getSelectedProduct, type FittingRoomState } from "./fittingRoomState";
import { ProductSwitchingError, type RequestOptions } from "./productSwitching";
import type { FittingRoomProduct } from "./types";

export const COLOR_SWITCH_PATH = "/api/fitting-room/switch-color";

export interface ColorSwitchRequest {
  product_id: string;
  category: string;
  color: string;
}

export interface ColorSwitchResponse {
  status: "found" | "not_found";
  requested_color: string;
  category: string;
  source: "variant" | "search" | null;
  product: FittingRoomProduct | null;
  reason: string | null;
}

export type ColorSwitchResult =
  | {
      kind: "replaced";
      slot: OutfitSlot;
      product: FittingRoomProduct;
      source: "variant" | "search" | null;
    }
  | { kind: "not_found"; requested_color: string; reason: string | null }
  | { kind: "already_selected" };

const COLOR_SPELLING: Readonly<Record<string, string>> = {
  gray: "grey",
  "navy blue": "navy",
};

/** Comparison key for color names (spelling variants only; no guessing). */
export function normalizeColorName(color: string | null | undefined): string | null {
  if (!color) return null;
  const cleaned = color.trim().toLowerCase().replace(/\s+/g, " ");
  if (cleaned === "") return null;
  return COLOR_SPELLING[cleaned] ?? cleaned;
}

function parseResponse(data: unknown): ColorSwitchResponse {
  const invalid = () =>
    new ProductSwitchingError("invalid_response", "Unexpected color-switch response shape.");

  if (typeof data !== "object" || data === null) throw invalid();
  const d = data as Record<string, unknown>;

  if (d.status !== "found" && d.status !== "not_found") throw invalid();
  if (typeof d.requested_color !== "string" || typeof d.category !== "string") throw invalid();

  if (d.product !== null && d.product !== undefined) {
    if (typeof d.product !== "object") throw invalid();
    const p = d.product as Record<string, unknown>;
    if (typeof p.product_id !== "string" || typeof p.category !== "string") throw invalid();
  }
  // Returned as-is: the objects the backend sent, unmodified.
  return data as ColorSwitchResponse;
}

export async function requestColorSwitch(
  request: ColorSwitchRequest,
  options: RequestOptions = {},
): Promise<ColorSwitchResponse> {
  const base = (options.baseUrl ?? "").replace(/\/+$/, "");

  let response: Response;
  try {
    response = await fetch(`${base}${COLOR_SWITCH_PATH}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal: options.signal,
    });
  } catch (err) {
    throw new ProductSwitchingError(
      "network",
      `Could not reach the backend: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body?.detail === "string") detail = `: ${body.detail}`;
    } catch {
      /* body was not JSON; the status is enough */
    }
    throw new ProductSwitchingError(
      "http",
      `Color switch request failed (${response.status})${detail}`,
      response.status,
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ProductSwitchingError("invalid_response", "Color switch response was not valid JSON.");
  }
  return parseResponse(data);
}

/**
 * Resolve `color` for whatever currently occupies `slot`. The category comes
 * from the slot (not from the product), so it works when the slot holds a
 * ColorVariation, which has no `category` field. The caller dispatches
 * SELECT_COLOR_PRODUCT only for a "replaced" result.
 */
export async function performColorSwitch(
  state: FittingRoomState,
  slot: OutfitSlot,
  color: string,
  options: RequestOptions = {},
): Promise<ColorSwitchResult> {
  const current = getSelectedProduct(state, slot);
  if (current === undefined) {
    throw new ProductSwitchingError("no_selection", `Nothing is selected in slot "${slot}".`);
  }

  const wanted = normalizeColorName(color);
  if (wanted !== null && wanted === normalizeColorName(current.color)) {
    return { kind: "already_selected" };
  }

  const response = await requestColorSwitch(
    { product_id: current.product_id, category: categoryForSlot(slot), color: color.trim() },
    options,
  );

  if (response.status === "not_found") {
    return {
      kind: "not_found",
      requested_color: response.requested_color,
      reason: response.reason ?? null,
    };
  }

  const product = response.product ?? null;
  if (product === null || slotForCategory(product.category) !== slot) {
    throw new ProductSwitchingError(
      "invalid_response",
      "Color switch returned no product for this slot.",
    );
  }

  return { kind: "replaced", slot, product, source: response.source ?? null };
}