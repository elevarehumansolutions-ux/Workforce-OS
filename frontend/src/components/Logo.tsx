import Image from "next/image";

// The Elevare OS ribbon mark (public/logo-mark.png) and the wordmark. The wordmark
// is live text so it stays readable on the dark theme: "Elevare" in white and "OS" in the brand orange.
const MARK_RATIO = 219 / 256;

export function LogoMark(props: { size?: number }) {
  const height = props.size || 36;
  return (
    <Image
      src="/logo-mark.png"
      alt=""
      width={Math.round(height * MARK_RATIO)}
      height={height}
      className="shrink-0"
    />
  );
}

export default function Logo(props: { size?: number; textClassName?: string }) {
  return (
    <>
      <LogoMark size={props.size} />
      <span className={props.textClassName || "text-base font-bold text-white"}>
        Elevare<span className="text-[#F47A00]">OS</span>
      </span>
    </>
  );
}