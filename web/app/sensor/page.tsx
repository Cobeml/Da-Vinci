import SensorGallery from "../../components/SensorGallery";
import data from "../../data/sensor-gallery.json";
export default function Page() {
  return <><div style={{maxWidth:1480,margin:"0 auto",padding:"20px 48px 0",fontSize:12}}><a href="/demo">← Object gallery</a></div><SensorGallery data={data} /></>;
}
