import GripperGallery from "../../components/GripperGallery";
import data from "../../data/gripper-gallery.json";
export default function Page() { return <><div style={{maxWidth:1480,margin:"0 auto",padding:"20px 48px 0",fontSize:12}}><a href="/demo">← Object gallery</a></div><GripperGallery data={data}/></>; }
