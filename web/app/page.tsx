import SensorGallery from "../components/SensorGallery";
import data from "../data/sensor-gallery.json";
export default function Page() {
  return <SensorGallery data={data} />;
}
