import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import { COLOR_SWITCH_PATH, performColorSwitch } from "./colorSwitching";
import {
  createInitialState,
  fittingRoomReducer,
  type FittingRoomState,
} from "./fittingRoomState";
import { ProductSwitchingError } from "./productSwitching";
import { makeProduct } from "./colorSwitchState.test";

const blackShirt = makeProduct({
  product_id: "MOCK001",
  color: "black",
  image_url: "https://cdn.mockfashionstore.test/images/mock001.jpg",
  product_url: "https://www.mockfashionstore.test/product/MOCK001",
});
const navyShirt = makeProduct({
  product_id: "MOCK003",
  color: "navy",
  image_url: "https://cdn.demostyle.test/images/mock003.jpg",
  product_url: "https://www.demostyle.test/product/MOCK003",
});
const pants = makeProduct({ product_id: "MOCK012", category: "pants", color: "cream" });
const shoes = makeProduct({ product_id: "MOCK027", category: "shoes", color: "brown" });
const watch = makeProduct({ product_id: "MOCK032", category: "watches", color: "silver" });

function outfitState(): FittingRoomState {
  let state = createInitialState("female");
  for (const product of [blackShirt, pants, shoes, watch]) {
    state = fittingRoomReducer(state, { type: "SELECT_PRODUCT", product });
  }
  return state;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const foundBody = {
  status: "found",
  requested_color: "navy",
  category: "shirts",
  source: "search",
  product: navyShirt,
  reason: null,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch() {
  const fetchMock = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("performColorSwitch", () => {
  it("asks the backend with the slot's current product and its category", async () => {
    const fetchMock = stubFetch();
    fetchMock.mockResolvedValueOnce(jsonResponse(foundBody));

    await performColorSwitch(outfitState(), "shirt", "navy");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(COLOR_SWITCH_PATH);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      product_id: "MOCK001",
      category: "shirts",
      color: "navy",
    });
  });

  it("returns the real product exactly as the backend sent it", async () => {
    stubFetch().mockResolvedValueOnce(jsonResponse(foundBody));

    const result = await performColorSwitch(outfitState(), "shirt", "navy");

    expect(result.kind).toBe("replaced");
    if (result.kind !== "replaced") return;
    expect(result.product).toEqual(navyShirt);
    expect(result.product.product_id).toBe("MOCK003");
    expect(result.product.image_url).toBe("https://cdn.demostyle.test/images/mock003.jpg");
    expect(result.product.product_url).toBe("https://www.demostyle.test/product/MOCK003");
  });

  it("changes only the shirt slot when the result is dispatched", async () => {
    stubFetch().mockResolvedValueOnce(jsonResponse(foundBody));
    const before = outfitState();

    const result = await performColorSwitch(before, "shirt", "navy");
    expect(result.kind).toBe("replaced");
    if (result.kind !== "replaced") return;

    const after = fittingRoomReducer(before, {
      type: "SELECT_COLOR_PRODUCT",
      slot: result.slot,
      product: result.product,
    });

    expect(after.selectedOutfit.shirt).toEqual(navyShirt);
    expect(after.selectedOutfit.pants).toBe(before.selectedOutfit.pants);
    expect(after.selectedOutfit.shoes).toBe(before.selectedOutfit.shoes);
    expect(after.selectedOutfit.watch).toBe(before.selectedOutfit.watch);
    expect(before.selectedOutfit.shirt).toBe(blackShirt); // previous state untouched
  });

  it("does not fabricate a product for an unavailable color", async () => {
    stubFetch().mockResolvedValueOnce(
      jsonResponse({
        status: "not_found",
        requested_color: "teal",
        category: "shirts",
        source: null,
        product: null,
        reason: "no_product_in_requested_color",
      }),
    );
    const before = outfitState();

    const result = await performColorSwitch(before, "shirt", "teal");

    expect(result).toEqual({
      kind: "not_found",
      requested_color: "teal",
      reason: "no_product_in_requested_color",
    });
    expect("product" in result).toBe(false);
    // Nothing to dispatch: the state is exactly what it was.
    expect(before.selectedOutfit.shirt).toBe(blackShirt);
  });

  it("makes no request when the requested color is already selected", async () => {
    const fetchMock = stubFetch();

    const result = await performColorSwitch(outfitState(), "shirt", "Black");

    expect(result).toEqual({ kind: "already_selected" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects when the slot is empty", async () => {
    const fetchMock = stubFetch();
    await expect(
      performColorSwitch(createInitialState("male"), "shirt", "navy"),
    ).rejects.toMatchObject({ kind: "no_selection" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a 'found' response whose product belongs to another slot", async () => {
    stubFetch().mockResolvedValueOnce(
      jsonResponse({ ...foundBody, product: makeProduct({ product_id: "MOCK013", category: "pants" }) }),
    );
    await expect(performColorSwitch(outfitState(), "shirt", "navy")).rejects.toMatchObject({
      kind: "invalid_response",
    });
  });

  it("rejects a 'found' response without a product", async () => {
    stubFetch().mockResolvedValueOnce(jsonResponse({ ...foundBody, product: null }));
    await expect(performColorSwitch(outfitState(), "shirt", "navy")).rejects.toBeInstanceOf(
      ProductSwitchingError,
    );
  });

  it("surfaces HTTP and network failures instead of inventing data", async () => {
    const fetchMock = stubFetch();
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "Invalid category" }, 422));
    await expect(performColorSwitch(outfitState(), "shirt", "navy")).rejects.toMatchObject({
      kind: "http",
      status: 422,
    });

    fetchMock.mockRejectedValueOnce(new Error("offline"));
    await expect(performColorSwitch(outfitState(), "shirt", "navy")).rejects.toMatchObject({
      kind: "network",
    });
  });
});

describe("no image recoloring exists in the fitting-room sources", () => {
  it("contains no CSS filter, canvas or pixel-manipulation code", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const forbidden =
      /hue-rotate|sepia\(|saturate\(|brightness\(|\bfilter\s*:|mix-blend-mode|feColorMatrix|getImageData|putImageData|<canvas|createElement\(\s*["']canvas["']/i;

    const sources = readdirSync(dir).filter(
      (name) => /\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name),
    );
    expect(sources.length).toBeGreaterThan(0);

    for (const name of sources) {
      const text = readFileSync(join(dir, name), "utf8");
      expect(forbidden.test(text), `${name} must not recolor images`).toBe(false);
    }
  });
});