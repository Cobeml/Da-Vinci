import type { Metadata } from "next";
import SurfaceGallery from "../../components/SurfaceGallery";
import data from "../../data/surface-gallery.json";

export const metadata: Metadata = {
  title: "Da Vinci — VTOL tools beta",
  description: "Paused experimental CAD tools and archived comparison results.",
  robots: { index: false, follow: false },
};

export default function Page() {
  return <SurfaceGallery data={data} />;
}
