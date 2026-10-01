"use client";

import { useCallback, useRef, useState } from "react";

import type { OutfitSlot } from "./categoryMap";
import { useFittingRoom } from "./FittingRoomProvider";
import {
  isAlternativeForSlot,
  ProductSwitchingError,
  requestAlternativesForSlot,
  type RequestOptions,
} from "./productSwitching";
import type { FittingRoomProduct } from "./types";

export interface AlternativesState {
  slot: OutfitSlot | null;
  /** "ready" with an empty `products` means the backend found none. */
  status: "idle" | "loading" | "ready" | "error";
  products: FittingRoomProduct[];
  error: ProductSwitchingError | null;
}

const IDLE: AlternativesState = { slot: null, status: "idle", products: [], error: null };

/** Must be used inside <FittingRoomProvider>. Selection goes through the existing SELECT_PRODUCT action. */
export function useProductSwitching(options?: RequestOptions) {
  const { state, selectProduct } = useFittingRoom();
  const [alternatives, setAlternatives] = useState<AlternativesState>(IDLE);
  const latest = useRef(0);

  const request = useCallback(
    async (slot: OutfitSlot) => {
      const id = ++latest.current;
      setAlternatives({ slot, status: "loading", products: [], error: null });
      try {
        const result = await requestAlternativesForSlot(state, slot, options);
        if (id !== latest.current) return; // a newer request superseded this one
        setAlternatives({ slot, status: "ready", products: result.products, error: null });
      } catch (err) {
        if (id !== latest.current) return;
        const error =
          err instanceof ProductSwitchingError
            ? err
            : new ProductSwitchingError("network", String(err));
        setAlternatives({ slot, status: "error", products: [], error });
      }
    },
    [state, options],
  );

  /** Returns false (and changes nothing) if the product doesn't belong to the requested slot. */
  const selectAlternative = useCallback(
    (product: FittingRoomProduct): boolean => {
      if (alternatives.slot === null || !isAlternativeForSlot(alternatives.slot, product)) {
        return false;
      }
      selectProduct(product);
      return true;
    },
    [alternatives.slot, selectProduct],
  );

  const reset = useCallback(() => {
    latest.current++;
    setAlternatives(IDLE);
  }, []);

  return { alternatives, requestAlternatives: request, selectAlternative, reset };
}