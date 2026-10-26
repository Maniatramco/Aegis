"use client";
export type SummaryTile={label:string;value:number|string;detail:string;tone:string};
/** Read-only counts at the top of a workspace screen. Styles live in page-template.css. */
export function SummaryTiles({tiles,label}:{tiles:SummaryTile[];label:string}){
 return <dl className="screen-summary" aria-label={label}>{tiles.map(tile=><div key={tile.label} className="screen-tile" data-tone={tile.tone||undefined}><dt>{tile.label}</dt><dd>{tile.value}</dd><span>{tile.detail}</span></div>)}</dl>;
}
