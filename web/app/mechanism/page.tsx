import RecordedStudy from "../../components/RecordedStudy";
import data from "../../public/studies/mechanism/report.json";
export const metadata = {title:"Da Vinci — vertical slider",description:"Recorded rigid-carriage revisions evaluated with MuJoCo under fixed motion and contact tests."};
export default function Page(){return <RecordedStudy data={data}/>;}
