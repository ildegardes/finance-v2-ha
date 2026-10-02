// One stroke-based SVG family shared by navigation, dashboard and actions.
const paths = {
 dashboard:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
 expense:'M12 3v18 M5 14l7 7 7-7', revenue:'M12 21V3 M5 10l7-7 7 7',
 card:'M3 5h18v14H3z M3 10h18 M7 15h3', invoice:'M6 3h12v18l-3-2-3 2-3-2-3 2z M9 7h6 M9 11h6',
 recurring:'M20 8a8 8 0 0 0-14-3L3 8 M3 3v5h5 M4 16a8 8 0 0 0 14 3l3-3 M21 21v-5h-5',
 installments:'M4 4h16v4H4z M4 10h16v4H4z M4 16h16v4H4z',
 catalogs:'M12 3v18 M3 12h18 M5 5l14 14 M5 19 19 5',
 check:'M4 12l5 5L20 6', undo:'M9 4 4 9l5 5 M4 9h10a6 6 0 0 1 0 12',
 edit:'M4 20l4-1L20 7l-3-3L5 16z M14 7l3 3', history:'M3 12a9 9 0 1 0 3-7 M3 3v5h5 M12 7v5l3 2',
 menu:'M4 6h16 M4 12h16 M4 18h16', more:'M5 12h.01 M12 12h.01 M19 12h.01',
 plus:'M12 4v16 M4 12h16', close:'M5 5l14 14 M5 19 19 5',
 left:'M15 5l-7 7 7 7', right:'M9 5l7 7-7 7', donut:'M12 3a9 9 0 1 0 9 9h-9z M15 3v6h6',
 clock:'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18 M12 7v5l3 2',
 wallet:'M3 6h17v14H3z M3 6V4h14 M15 11h6v5h-6z', trend:'M3 17l6-6 4 4 8-10 M16 5h5v5'
};
const aliases={income:'revenue',outcome:'expense',balance:'wallet',chart:'trend',calendar:'clock',repeat:'recurring',activity:'history',eye:'history',alert:'clock'};
export function icon(name,title=null){return `<svg class="ui-icon ${name}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${title?'role="img" aria-label="'+title+'"':'aria-hidden="true"'}><path d="${paths[aliases[name]||name]||paths.history}"/></svg>`}
