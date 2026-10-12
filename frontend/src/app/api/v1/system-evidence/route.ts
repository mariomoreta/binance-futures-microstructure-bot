import {canonicalSystemEvidence} from "@/lib/system-evidence";
export const dynamic="force-dynamic";
export function GET(){
 const data=canonicalSystemEvidence();
 return Response.json(data,{status:data.available?200:503,headers:{"Cache-Control":"no-store"}});
}
