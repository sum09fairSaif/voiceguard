import { useEffect, useRef } from "react";

// True while the screen is on view, false once the user has left it. A
// request that finishes after that checks it and does nothing, so a late
// answer can't sign someone in or move them somewhere they didn't choose.
export function useStillShown() {
  const shown = useRef(true);
  useEffect(() => {
    shown.current = true;
    return () => {
      shown.current = false;
    };
  }, []);
  return shown;
}
