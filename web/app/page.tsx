import GripperGallery from "../components/GripperGallery";
import SensorGallery from "../components/SensorGallery";
import data from "../data/gripper-gallery.json";
import sensorData from "../data/sensor-gallery.json";
export default function Page() {
  return data.publishable ? <GripperGallery data={data} /> : <SensorGallery data={sensorData} />;
}
