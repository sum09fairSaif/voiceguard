import { isAxiosError } from "axios";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { describeApiError } from "../api/errors";
import { getMe, type Me } from "../api/me";
import { endSession } from "../api/session";

// The account summary for the signed-in screens (Home and Settings). The
// server decides who may see it: it answers 403 to a password alone and 401
// to a missing or expired session, and this follows that.
export function useMe(): { me: Me | null; error: string } {
  const navigate = useNavigate();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");
  // React's development mode mounts screens twice.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    getMe()
      .then(setMe)
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
  }, [navigate]);

  return { me, error };
}
