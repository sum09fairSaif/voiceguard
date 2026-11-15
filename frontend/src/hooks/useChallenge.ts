import { isAxiosError } from "axios";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { requestChallenge, type Challenge } from "../api/challenge";
import { clearToken } from "../api/session";
import { describeVoiceCheckError, isVoiceCheckPaused } from "../api/verify";
import { secondsLeft } from "../utils/countdown";

export type ChallengeState = {
  challenge: Challenge | null;
  loading: boolean;
  error: string;
  secondsRemaining: number;
  expired: boolean;
  // Voice checks are paused for this account (423): no passage until the wait is over.
  paused: boolean;
  newPhrase: () => void;
};

// Fetches a passage when the screen opens, counts down to its expiry, and
// fetches a fresh one on request. Only the newest attempt is ever kept:
// asking for a new passage cancels the previous one on the server.
export function useChallenge(): ChallengeState {
  const navigate = useNavigate();
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [paused, setPaused] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  // Numbers each request so a slow earlier reply can't replace a newer one.
  const latestRequest = useRef(0);
  // React's development mode mounts screens twice; without this, opening
  // the screen would use up two passages of the hourly limit.
  const started = useRef(false);

  const fetchChallenge = useCallback(async () => {
    const requestId = ++latestRequest.current;
    try {
      const next = await requestChallenge();
      if (requestId !== latestRequest.current) return;
      setChallenge(next);
      setError("");
      setPaused(false);
      setNow(Date.now());
    } catch (err) {
      if (requestId !== latestRequest.current) return;
      if (isAxiosError(err) && err.response?.status === 401) {
        clearToken();
        navigate("/signin", { replace: true });
        return;
      }
      setChallenge(null);
      setPaused(isVoiceCheckPaused(err));
      setError(describeVoiceCheckError(err, {}));
    } finally {
      if (requestId === latestRequest.current) setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void fetchChallenge();
  }, [fetchChallenge]);

  const newPhrase = useCallback(() => {
    setLoading(true);
    setError("");
    void fetchChallenge();
  }, [fetchChallenge]);

  const secondsRemaining = challenge ? secondsLeft(challenge.expires_at, now) : 0;
  const expired = challenge !== null && secondsRemaining === 0;

  useEffect(() => {
    if (!challenge || expired) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [challenge, expired]);

  return { challenge, loading, error, secondsRemaining, expired, paused, newPhrase };
}
