import VTOLGallery from "../components/VTOLGallery";
import GripperGallery from "../components/GripperGallery";
import SensorGallery from "../components/SensorGallery";
import vtol from "../data/vtol-gallery.json";
import data from "../data/gripper-gallery.json";
import sensorData from "../data/sensor-gallery.json";
import SurfaceGallery from "../components/SurfaceGallery";
import surface from "../data/surface-gallery.json";
export default function Page() {
  return surface.publishable ? <SurfaceGallery data={surface}/> : vtol.publishable ? <VTOLGallery data={vtol}/> : data.publishable ? <GripperGallery data={data} /> : <SensorGallery data={sensorData} />;
}
