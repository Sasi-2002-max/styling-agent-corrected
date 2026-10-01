"use client";

import { useCallback, useRef, useState } from "react";

import type { OutfitSlot } from "./categoryMap";
import { performColorSwitch } from "./colorSwitching";
import { useFittingRoom } from "./FittingRoomProvider";
import { ProductSwitchingError, type RequestOptions } from "./productSwitching";

export interface ColorSwitchState {
  slot: OutfitSlot | null;
  requestedColor: string | null;
  status: "idle" | "loading" | "replaced" | "not_found" | "already_selected" | "error";
  reason: string | null;
  error: ProductSwitchingError | null;
}

const IDLE: ColorSwitchState = {
  slot: null,
  requestedColor: null,
  status: "idle",
  reason: null,
  error: null,
};

/**
 * Must be used inside <FittingRoomProvider>. Only a "replaced" result changes
 * state, and only the requested slot changes (via SELECT_COLOR_PRODUCT).
 */
export function useColorSwitching(options?: RequestOptions) {
  const { state, selectColorProduct } = useFittingRoom();
  const [colorSwitch, setColorSwitch] = useState<ColorSwitchState>(IDLE);
  const latest = useRef(0);

  const switchColor = useCallback(
    async (slot: OutfitSlot, color: string) => {
      const id = ++latest.current;
      setColorSwitch({ slot, requestedColor: color, status: "loading", reason: null, error: null });
      try {
        const result = await performColorSwitch(state, slot, color, options);
        if (id !== latest.current) return; // a newer request superseded this one

        if (result.kind === "replaced") {
          selectColorProduct(result.slot, result.product);
          setColorSwitch({ slot, requestedColor: color, status: "replaced", reason: null, error: null });
        } else if (result.kind === "not_found") {
          // Current product stays; nothing is fabricated.
          setColorSwitch({
            slot,
            requestedColor: color,
            status: "not_found",
            reason: result.reason,
            error: null,
          });
        } else {
          setColorSwitch({
            slot,
            requestedColor: color,
            status: "already_selected",
            reason: null,
            error: null,
          });
        }
      } catch (err) {
        if (id !== latest.current) return;
        const error =
          err instanceof ProductSwitchingError
            ? err
            : new ProductSwitchingError("network", String(err));
        setColorSwitch({ slot, requestedColor: color, status: "error", reason: null, error });
      }
    },
    [state, options, selectColorProduct],
  );

  const reset = useCallback(() => {
    latest.current++;
    setColorSwitch(IDLE);
  }, []);

  return { colorSwitch, switchColor, reset };
}