// "Yellowstone National Park" is the badge; in a row, a button or a phone's
// top bar the word everyone uses is enough.
export function shortPark(name: string): string {
  return name.replace(/ National Park( and Preserve)?$/, "").replace(/ National Parks$/, "").replace(/^National Park of /, "");
}
