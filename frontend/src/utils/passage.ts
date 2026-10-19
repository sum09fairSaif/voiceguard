// The passage is always lowercase words; a capital first letter reads better.
// Display only: what the user must say is unchanged.
export function displayPassage(passage: string): string {
  return passage.charAt(0).toUpperCase() + passage.slice(1);
}
