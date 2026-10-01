import { afterEach, describe, expect, it, vi } from "vitest";

import { createInitialState, fittingRoomReducer, getSelectedProduct, type FittingRoomState } from "./fittingRoomState";
import {
  ALTERNATIVES_PATH,
  isAlternativeForSlot,
  ProductSwitchingError,
  requestAlternatives,
  requestAlternativesForSlot,
} from "./productSwitching";
import type { ColorVariation, FittingRoomProduct } from "./types";

// ---- TEST FIXTURE DATA ONLY (not a catalog) --------------------------------

function product(o: Partial<FittingRoomProduct> & { product_id: string }): FittingRoomProduct {
  return {
    store: "Demo Fashion",
    brand: "Urban Weave",
    title: `Item ${o.product_id}`,
    category: "shirts",
    color: "black",
    price: 1000,
    currency: "INR",
    sizes: ["M"],
    image_url: `https://example.test/${o.product_id}.jpg`,
    product_url: `https://example.test/${o.product_id}`,
    availability: true,
    ...o,
  };
}

const SHIRT = product({ product_id: "AMZ123", category: "shirts" });
const PANTS = product({ product_id: "MYN456", category: "pants", color: "cream" });
const SHOES = product({ product_id: "AJ789", category: "shoes", image_url: null });

function selected(): FittingRoomState {
  let s = createInitialState("female");
  for (const p of [SHIRT, PANTS, SHOES]) {
    s = fittingRoomReducer(s, { type: "SELECT_PRODUCT", product: p });
  }
  return s;
}

function mockFetch(body: unknown, init: { ok?: boolean; status?: number } = {}) {
  const fn = vi.fn(async (_url: string, _init?: RequestInit) => ({
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
  }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function sentBody(fn: ReturnType<typeof mockFetch>) {
  const [, init] = fn.mock.calls[0]!;
  return JSON.parse(String(init?.body));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("requesting alternatives", () => {
  it("1. requests shirt alternatives", async () => {
    const alt = product({ product_id: "AMZ124", category: "shirts" });
    const fn = mockFetch({ category: "shirts", products: [alt] });

    const result = await requestAlternativesForSlot(selected(), "shirt");

    const [url, init] = fn.mock.calls[0]!;
    expect(url).toBe(ALTERNATIVES_PATH);
    expect(init?.method).toBe("POST");
    expect(sentBody(fn)).toEqual({ product_id: "AMZ123", category: "shirts" });
    expect(result.products[0]).toBe(alt);
  });

  it("2. requests pants alternatives", async () => {
    const fn = mockFetch({ category: "pants", products: [] });
    await requestAlternativesForSlot(selected(), "pants");
    expect(sentBody(fn)).toEqual({ product_id: "MYN456", category: "pants" });
  });

  it("3. requests shoes alternatives", async () => {
    const fn = mockFetch({ category: "shoes", products: [] });
    await requestAlternativesForSlot(selected(), "shoes");
    expect(sentBody(fn)).toEqual({ product_id: "AJ789", category: "shoes" });
  });

  it("uses the slot's category when the slot holds a color variation", async () => {
    const variation: ColorVariation = {
      product_id: "AMZ123-WHITE",
      color: "white",
      image_url: null,
      product_url: "https://example.test/AMZ123-WHITE",
      price: 1299,
      currency: "INR",
    };
    const s = fittingRoomReducer(selected(), { type: "SELECT_VARIATION", slot: "shirt", variation });
    const fn = mockFetch({ category: "shirts", products: [] });
    await requestAlternativesForSlot(s, "shirt");
    expect(sentBody(fn)).toEqual({ product_id: "AMZ123-WHITE", category: "shirts" });
  });

  it("makes no request for an empty slot", async () => {
    const fn = mockFetch({ category: "watches", products: [] });
    await expect(requestAlternativesForSlot(selected(), "watch")).rejects.toMatchObject({
      kind: "no_selection",
    });
    expect(fn).not.toHaveBeenCalled();
  });

  it("prefixes baseUrl", async () => {
    const fn = mockFetch({ category: "shirts", products: [] });
    await requestAlternatives(
      { product_id: "AMZ123", category: "shirts" },
      { baseUrl: "http://127.0.0.1:8000/" },
    );
    expect(fn.mock.calls[0]![0]).toBe("http://127.0.0.1:8000/api/fitting-room/alternatives");
  });
});

describe("selecting an alternative (existing SELECT_PRODUCT)", () => {
  const alt = product({ product_id: "AMZ124", category: "shirts", color: "blue" });

  it("4-5. updates only that slot; other slots keep identity", async () => {
    mockFetch({ category: "shirts", products: [alt] });
    const before = selected();
    const { products } = await requestAlternativesForSlot(before, "shirt");

    const after = fittingRoomReducer(before, { type: "SELECT_PRODUCT", product: products[0]! });

    expect(after.selectedOutfit.shirt).toBe(alt);
    expect(after.selectedOutfit.pants).toBe(PANTS);
    expect(after.selectedOutfit.shoes).toBe(SHOES);
    expect(after.selectedOutfit.mannequin).toBe("female");
  });

  it("6. the selected object is the backend object, unchanged", async () => {
    const fn = mockFetch({ category: "shirts", products: [alt] });
    const { products } = await requestAlternativesForSlot(selected(), "shirt");
    const s = fittingRoomReducer(selected(), { type: "SELECT_PRODUCT", product: products[0]! });
    const shirt = getSelectedProduct(s, "shirt")!;
    expect(shirt).toBe(alt);
    expect(shirt).toEqual({ ...alt });
    expect(shirt.image_url).toBe(alt.image_url);
    expect(shirt.product_url).toBe(alt.product_url);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("guards against an alternative from a different category", () => {
    expect(isAlternativeForSlot("shirt", alt)).toBe(true);
    expect(isAlternativeForSlot("pants", alt)).toBe(false);
    expect(isAlternativeForSlot("shirt", product({ product_id: "X", category: "hats" }))).toBe(false);
  });
});

describe("no fake products", () => {
  it("7. returns only objects the backend supplied, with null image_url kept", async () => {
    const a = product({ product_id: "AMZ124" });
    const b = product({ product_id: "AMZ125", image_url: null });
    mockFetch({ category: "shirts", products: [a, b] });
    const { products } = await requestAlternativesForSlot(selected(), "shirt");
    expect(products).toHaveLength(2);
    expect(products[0]).toBe(a);
    expect(products[1]).toBe(b);
    expect(products[1]!.image_url).toBeNull();
  });
});

describe("empty and failure handling", () => {
  it("8. empty alternatives stay empty", async () => {
    mockFetch({ category: "shirts", products: [] });
    const result = await requestAlternativesForSlot(selected(), "shirt");
    expect(result.products).toEqual([]);
  });

  it("9. network failure -> ProductSwitchingError(network), no products", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = await requestAlternativesForSlot(selected(), "shirt").catch((e) => e);
    expect(err).toBeInstanceOf(ProductSwitchingError);
    expect(err.kind).toBe("network");
  });

  it("9. HTTP 500 (MCP / shopping failure) -> http error with status", async () => {
    mockFetch({ detail: "boom" }, { ok: false, status: 500 });
    const err = await requestAlternativesForSlot(selected(), "shirt").catch((e) => e);
    expect(err).toMatchObject({ kind: "http", status: 500 });
  });

  it("9. HTTP 422 (invalid category) surfaces the backend detail", async () => {
    mockFetch({ detail: "Invalid category: 'hats'." }, { ok: false, status: 422 });
    const err = await requestAlternatives({ product_id: "X", category: "hats" }).catch((e) => e);
    expect(err).toMatchObject({ kind: "http", status: 422 });
    expect(err.message).toContain("Invalid category");
  });

  it("rejects a malformed 200 response instead of guessing", async () => {
    mockFetch({ products: "nope" });
    const err = await requestAlternativesForSlot(selected(), "shirt").catch((e) => e);
    expect(err).toMatchObject({ kind: "invalid_response" });
  });

  it("a failed request leaves state untouched", async () => {
    mockFetch({ detail: "boom" }, { ok: false, status: 500 });
    const before = selected();
    await requestAlternativesForSlot(before, "shirt").catch(() => undefined);
    expect(before.selectedOutfit.shirt).toBe(SHIRT);
  });
});