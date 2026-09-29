import VTOLGallery from "../components/VTOLGallery";
import GripperGallery from "../components/GripperGallery";
import SensorGallery from "../components/SensorGallery";
import vtol from "../data/vtol-gallery.json";
import data from "../data/gripper-gallery.json";
import sensorData from "../data/sensor-gallery.json";
export default function Page() {
  return vtol.publishable ? <VTOLGallery data={vtol}/> : data.publishable ? <GripperGallery data={data} /> : <SensorGallery data={sensorData} />;
}
