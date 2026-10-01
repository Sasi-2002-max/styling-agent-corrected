import { describe, expect, it } from "vitest";

import {
  createInitialState,
  fittingRoomReducer,
  type FittingRoomState,
} from "./fittingRoomState";
import type { FittingRoomProduct } from "./types";

export function makeProduct(over: Partial<FittingRoomProduct>): FittingRoomProduct {
  return {
    product_id: "X",
    store: "Demo Fashion",
    brand: "Brand",
    title: "Title",
    category: "shirts",
    color: "black",
    price: 1000,
    currency: "INR",
    sizes: ["M"],
    image_url: "https://cdn.example.test/x.jpg",
    product_url: "https://www.example.test/product/X",
    availability: true,
    ...over,
  };
}

const blackShirt = makeProduct({
  product_id: "MOCK001",
  title: "Black Oxford Shirt",
  color: "black",
  image_url: "https://cdn.mockfashionstore.test/images/mock001.jpg",
  product_url: "https://www.mockfashionstore.test/product/MOCK001",
});
const navyShirt = makeProduct({
  product_id: "MOCK003",
  title: "Navy Casual Shirt",
  color: "navy",
  image_url: null, // real catalog product without an image
  product_url: "https://www.demostyle.test/product/MOCK003",
});
const pants = makeProduct({ product_id: "MOCK012", category: "pants", color: "cream" });
const shoes = makeProduct({ product_id: "MOCK027", category: "shoes", color: "brown" });
const watch = makeProduct({ product_id: "MOCK032", category: "watches", color: "silver" });

function deepFreeze<T>(value: T): T {
  if (typeof value === "object" && value !== null && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.values(value as Record<string, unknown>).forEach(deepFreeze);
  }
  return value;
}

function outfitState(): FittingRoomState {
  let state = createInitialState("male");
  for (const product of [blackShirt, pants, shoes, watch]) {
    state = fittingRoomReducer(state, { type: "SELECT_PRODUCT", product });
  }
  return state;
}

describe("SELECT_COLOR_PRODUCT", () => {
  it("replaces only the target slot with the real product", () => {
    const before = outfitState();
    const after = fittingRoomReducer(before, {
      type: "SELECT_COLOR_PRODUCT",
      slot: "shirt",
      product: navyShirt,
    });

    expect(after).not.toBe(before);
    expect(after.selectedOutfit.shirt).toBe(navyShirt);
    expect(after.selectedOutfit.pants).toBe(before.selectedOutfit.pants);
    expect(after.selectedOutfit.shoes).toBe(before.selectedOutfit.shoes);
    expect(after.selectedOutfit.watch).toBe(before.selectedOutfit.watch);
    expect(after.selectedOutfit.mannequin).toBe("male");
  });

  it("preserves product_id, image_url and product_url exactly", () => {
    const after = fittingRoomReducer(outfitState(), {
      type: "SELECT_COLOR_PRODUCT",
      slot: "shirt",
      product: navyShirt,
    });
    const shirt = after.selectedOutfit.shirt!;

    expect(shirt.product_id).toBe("MOCK003");
    expect(shirt.image_url).toBeNull(); // null stays null, never a placeholder
    expect(shirt.product_url).toBe("https://www.demostyle.test/product/MOCK003");
    expect(shirt.color).toBe("navy");
  });

  it("does not mutate the previous state", () => {
    const before = deepFreeze(outfitState());
    const after = fittingRoomReducer(before, {
      type: "SELECT_COLOR_PRODUCT",
      slot: "shirt",
      product: navyShirt,
    });

    expect(before.selectedOutfit.shirt).toBe(blackShirt);
    expect(before.selectedOutfit.shirt!.product_id).toBe("MOCK001");
    expect(after.selectedOutfit.shirt).toBe(navyShirt);
  });

  it("ignores a product that belongs to a different slot", () => {
    const before = outfitState();
    const after = fittingRoomReducer(before, {
      type: "SELECT_COLOR_PRODUCT",
      slot: "shirt",
      product: makeProduct({ product_id: "MOCK013", category: "pants", color: "navy" }),
    });
    expect(after).toBe(before);
  });

  it("ignores an unknown slot", () => {
    const before = outfitState();
    const after = fittingRoomReducer(before, {
      type: "SELECT_COLOR_PRODUCT",
      slot: "spaceship" as never,
      product: navyShirt,
    });
    expect(after).toBe(before);
  });
});