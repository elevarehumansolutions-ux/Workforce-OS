// For boxes that take a plain number (a weight, a target). Keeps only the digits and
// the first decimal point, so a typed or pasted "22%" becomes "22" and "1,500" becomes
// "1500". Used on every change, so a letter simply never appears in the box.
export function keepOnlyNumber(text: string): string {
  let result = "";
  let seenDot = false;
  for (const ch of text) {
    if (ch >= "0" && ch <= "9") {
      result = result + ch;
    } else if (ch === "." && !seenDot) {
      result = result + ch;
      seenDot = true;
    }
  }
  return result;
}
