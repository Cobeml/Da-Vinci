import RecordedStudy from "../../components/RecordedStudy";
import data from "../../public/studies/structural/report.json";
export const metadata = {title:"Da Vinci — structural bracket",description:"Recorded bracket revisions evaluated with Gmsh and CalculiX under a frozen linear-static test contract."};
export default function Page(){return <RecordedStudy data={data}/>;}
