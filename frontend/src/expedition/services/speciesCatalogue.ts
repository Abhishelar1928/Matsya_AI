/**
 * Approved Maharashtra Commercial Marine Fish Species Catalogue (EN / MR / Scientific).
 * Packaged with offline expeditions so offline catch logging uses canonical identifiers.
 */

export interface SpeciesEntry {
  id: string;
  en: string;
  mr: string;
  scientific: string;
  category: 'pelagic' | 'demersal' | 'crustacean' | 'cephalopod' | 'other';
}

export const MAHARASHTRA_SPECIES: SpeciesEntry[] = [
  { id: 'pomfret_silver', en: 'Silver Pomfret', mr: 'पापलेट (सफेद)', scientific: 'Pampus argenteus', category: 'pelagic' },
  { id: 'pomfret_black', en: 'Black Pomfret', mr: 'हलवा', scientific: 'Parastromateus niger', category: 'pelagic' },
  { id: 'bombay_duck', en: 'Bombay Duck', mr: 'बोंबील', scientific: 'Harpadon nehereus', category: 'pelagic' },
  { id: 'mackerel', en: 'Indian Mackerel', mr: 'बांगडा', scientific: 'Rastrelliger kanagurta', category: 'pelagic' },
  { id: 'sardine', en: 'Oil Sardine', mr: 'तारली', scientific: 'Sardinella longiceps', category: 'pelagic' },
  { id: 'prawn', en: 'Prawn / Shrimp', mr: 'कोळंबी', scientific: 'Penaeus / Metapenaeus spp.', category: 'crustacean' },
  { id: 'surmai', en: 'Kingfish / Surmai', mr: 'सुरमई', scientific: 'Scomberomorus commerson', category: 'pelagic' },
  { id: 'rawas', en: 'Indian Salmon (Rawas)', mr: 'रावस', scientific: 'Eleutheronema tetradactylum', category: 'demersal' },
  { id: 'ghol', en: 'Blackspotted Croaker (Ghol)', mr: 'घोळ', scientific: 'Protonibea diacanthus', category: 'demersal' },
  { id: 'koth', en: 'Croaker (Koth / Dhoma)', mr: 'ढोमा / कोथ', scientific: 'Otolithoides biauritus', category: 'demersal' },
  { id: 'squid', en: 'Squid', mr: 'माकूळ', scientific: 'Uroteuthis duvaucelii', category: 'cephalopod' },
  { id: 'cuttlefish', en: 'Cuttlefish', mr: 'गोट्या माकूळ', scientific: 'Sepia pharaonis', category: 'cephalopod' },
  { id: 'tuna', en: 'Yellowfin / Skipjack Tuna', mr: 'कुपा', scientific: 'Thunnus / Katsuwonus spp.', category: 'pelagic' },
  { id: 'ribbonfish', en: 'Ribbonfish', mr: 'वागटी / बाला', scientific: 'Trichiurus lepturus', category: 'demersal' },
  { id: 'lobster', en: 'Spiny Lobster', mr: 'शेवंड', scientific: 'Panulirus polyphagus', category: 'crustacean' },
  { id: 'other', en: 'Other / Mixed Catch', mr: 'इतर', scientific: 'Unclassified', category: 'other' },
];

export function findSpecies(speciesIdOrEn: string): SpeciesEntry | undefined {
  return MAHARASHTRA_SPECIES.find(
    (s) => s.id === speciesIdOrEn || s.en.toLowerCase() === speciesIdOrEn.toLowerCase(),
  );
}
