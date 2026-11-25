import { isAxiosError } from "axios";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { describeApiError } from "../api/errors";
import { endSession } from "../api/session";

// Loads something only a voice-verified session may see (the account,
// its activity). The server decides who may: it answers 403 to a password
// alone and 401 to a missing or expired session, and this follows that.
export function useSignedInData<T>(load: () => Promise<T>): { data: T | null; error: string } {
  const navigate = useNavigate();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  // React's development mode mounts screens twice.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    load()
      .then(setData)
      .catch((err) => {
        const status = isAxiosError(err) ? err.response?.status : undefined;
        if (status === 401) {
          endSession();
          navigate("/signin", { replace: true });
        } else if (status === 403) {
          // Signed in with a password, but the voice check isn't done.
          navigate("/verify", { replace: true });
        } else {
          setError(describeApiError(err));
        }
      });
  }, [load, navigate]);

  return { data, error };
}
