import { getMe, type Me } from "../api/me";
import { useSignedInData } from "./useSignedInData";

// The account summary for the signed-in screens (Home and Settings).
export function useMe(): { me: Me | null; error: string } {
  const { data, error } = useSignedInData(getMe);
  return { me: data, error };
}
