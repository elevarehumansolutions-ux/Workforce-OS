import type { MeData } from "@/lib/settings";

// Every settings section gets the signed-in person's details so it can hide
// what they may not use. The server still decides what is actually allowed.
export interface SectionProps {
  me: MeData;
}
