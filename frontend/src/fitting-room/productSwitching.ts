/**
 * Product switching (Part 45) -- client for POST /api/fitting-room/alternatives.
 *
 * The frontend never searches or ranks. It asks the backend for alternatives
 * and returns exactly the objects the backend sent. Failures throw
 * ProductSwitchingError; they are never turned into fake products, and an
 * empty result stays empty.
 */

import { categoryForSlot, slotForCategory, type OutfitSlot } from "./categoryMap";
import { getSelectedProduct, type FittingRoomState } from "./fittingRoomState";
import type { FittingRoomProduct } from "./types";

export const ALTERNATIVES_PATH = "/api/fitting-room/alternatives";

export interface AlternativesRequest {
  product_id: string;
  category: string;
}

export interface AlternativesResponse {
  category: string;
  products: FittingRoomProduct[];
}

export interface RequestOptions {
  /** Backend origin, e.g. "http://127.0.0.1:8000". Defaults to same-origin. */
  baseUrl?: string;
  signal?: AbortSignal;
}

export type ProductSwitchingErrorKind =
  | "no_selection" // the slot is empty, so there is no product to switch from
  | "network" // backend unreachable
  | "http" // non-2xx: 422 invalid category, 500 MCP/shopping failure, ...
  | "invalid_response"; // 2xx but not the documented shape

export class ProductSwitchingError extends Error {
  readonly kind: ProductSwitchingErrorKind;
  readonly status?: number;

  constructor(kind: ProductSwitchingErrorKind, message: string, status?: number) {
    super(message);
    this.name = "ProductSwitchingError";
    this.kind = kind;
    this.status = status;
  }
}

function parseResponse(data: unknown): AlternativesResponse {
  const invalid = () =>
    new ProductSwitchingError("invalid_response", "Unexpected alternatives response shape.");

  if (typeof data !== "object" || data === null) throw invalid();
  const d = data as Record<string, unknown>;
  if (typeof d.category !== "string" || !Array.isArray(d.products)) throw invalid();

  for (const p of d.products as unknown[]) {
    if (
      typeof p !== "object" ||
      p === null ||
      typeof (p as Record<string, unknown>).product_id !== "string"
    ) {
      throw invalid();
    }
  }
  // Returned as-is: the very objects the backend sent, unmodified.
  return data as AlternativesResponse;
}

export async function requestAlternatives(
  request: AlternativesRequest,
  options: RequestOptions = {},
): Promise<AlternativesResponse> {
  const base = (options.baseUrl ?? "").replace(/\/+$/, "");

  let response: Response;
  try {
    response = await fetch(`${base}${ALTERNATIVES_PATH}`, {
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
      `Alternatives request failed (${response.status})${detail}`,
      response.status,
    );
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ProductSwitchingError("invalid_response", "Alternatives response was not valid JSON.");
  }
  return parseResponse(data);
}

/**
 * Ask for alternatives to whatever currently occupies `slot`. The category is
 * derived from the slot, so it also works when the slot holds a ColorVariation
 * (which has no `category` field).
 */
export function requestAlternativesForSlot(
  state: FittingRoomState,
  slot: OutfitSlot,
  options: RequestOptions = {},
): Promise<AlternativesResponse> {
  const current = getSelectedProduct(state, slot);
  if (current === undefined) {
    return Promise.reject(
      new ProductSwitchingError("no_selection", `Nothing is selected in slot "${slot}".`),
    );
  }
  return requestAlternatives(
    { product_id: current.product_id, category: categoryForSlot(slot) },
    options,
  );
}

/**
 * Guard: an alternative may only replace the slot it was requested for.
 * SELECT_PRODUCT derives the slot from product.category, so a product of a
 * different category would otherwise land in another slot.
 */
export function isAlternativeForSlot(slot: OutfitSlot, product: FittingRoomProduct): boolean {
  return slotForCategory(product.category) === slot;
}