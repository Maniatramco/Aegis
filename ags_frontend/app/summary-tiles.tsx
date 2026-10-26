"use client";
import './needs-attention.css';
import {openAttention,type AttentionScope} from './needs-attention';
export type SummaryTile={label:string;value:number|string;detail:string;tone:string;attention?:AttentionScope};
/** Counts at the top of a workspace screen; a non-zero "needs attention" count opens the shared pop-up. Styles live in page-template.css. */
export function SummaryTiles({tiles,label}:{tiles:SummaryTile[];label:string}){
 return <dl className="screen-summary" aria-label={label}>{tiles.map(tile=>{const actionable=Boolean(tile.attention)&&Number(tile.value)>0;
  return <div key={tile.label} className={`screen-tile${actionable?' screen-tile-actionable':''}`} data-tone={tile.tone||undefined}><dt>{tile.label}</dt><dd>{tile.value}</dd><span>{tile.detail}</span>{actionable&&<button type="button" className="screen-tile-cta attention-trigger" onClick={()=>openAttention(tile.attention)}>Review and fix</button>}</div>;})}</dl>;
}
