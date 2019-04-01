import re
from collections import defaultdict

# See https://fi.wikipedia.org/wiki/Helsingin_seudun_liikenne#J%C3%A4senkunnat
cities = [ "Helsinki", "Espoo", "Vantaa", "Kirkkonummi", "Kerava",
    "Kauniainen", "Sipoo", "Tuusula", "Siuntio" ]

# Cities with some bus stops with HSL code
extracities_bus = [ "Järvenpää", "Mäntsälä", "Nurmijärvi", "Pornainen",
    "Porvoo" ]

modecolors = { "bus": "#007AC9",
    "tram":     "#00985F",
    "train":    "#8C4799",
    "subway":   "#FF6319",
    "ferry":    "#00B9E4",
    "aerialway": None,
    "monorail": None,
    "trolleybus": None
}

peakhours = [(7, 9), (15,18)]
# HSL night services start at 23, but use midnight to avoid overlap with
# normal services.
nighthours = [(0, 5)]

# Assigned bus code prefixes for cities
prefix2city = {
    "": "Helsinki",
    "E": "Espoo",
    "H": "Helsinki",
    "Hy": "Hyvinkää",
    "Jä": "Järvenpää",
    "Ka": "Kauniainen",
    "Ke": "Kerava",
    "Ki": "Kirkkonummi",
    "La": "Lahti",
    "Mä": "Mäntsälä",
    "Nu": "Nurmijärvi",
    "Pn": "Pornainen",
    "Po": "Porvoo",
    "Ri": "Riihimäki",
    "Si": "Sipoo",
    "So": "Siuntio",
    "Tu": "Tuusula",
    "V": "Vantaa",
}

city2prefixes = defaultdict(list)
for p,c in prefix2city.items():
    city2prefixes[c].append(p)

# See https://fi.wikipedia.org/wiki/Luettelo_Suomen_kuntanumeroista
city2ref = {
    "Espoo": "049",
    "Helsinki": "091",
    "Hyvinkää": "106",
    "Järvenpää": "186",
    "Kauniainen": "235",
    "Kerava": "245",
    "Kirkkonummi": "257",
    "Kouvola": "286",
    "Lahti": "398",
    "Mäntsälä": "505",
    "Nurmijärvi": "543",
    "Pornainen": "611",
    "Porvoo": "638",
    "Riihimäki": "694",
    "Sipoo": "753",
    "Siuntio": "755",
    "Tuusula": "858",
    "Vantaa": "092",
}


zoneid2name = {
    "01": "A",
    "02": "B",
    "04": "C",
    "06": "D", # Kirkkonummi, Siuntio
    "09": "D", # Tuusula, Kerava, Sipoo
    "99": "no",
}


synonyms = [
    ('A. Petreliuksen', 'Albert Petreliuksen'),
    ('Aleksant.', 'Aleksanterin'),
    ('Aurinkol.', 'Aurinkolahden'),
    ('Etel.', 'Eteläinen'),
    ('G. Paulig', 'Gustav Paulig'),
    ('Hels.pit.', 'Helsingin pitäjän'),
    ('Hertton.terv.as.', 'Herttoniemen terveysasema'),
    ('Juhana Herttuan', 'Juhana-herttuan'),
    ('Järvenpää L.-autoas.', 'Järvenpään linja-autoasema'),
    ('Laversinti', 'Laversintie'),
    ('Luonnontiet.', 'Luonnontieteellinen'),
    ('Martinl. terv. asema', 'Martinlaakson terveysasema'),
    ('Munkkin.', 'Munkkiniemen'),
    ('Pohj.', 'Pohjoinen'),
    ('Saariselän palvelut.', 'Saariseläntien palvelutalo'),
    ('Saariselänt. palv.t.', 'Saariseläntien palvelutalo'),
    ('Sipoonl. levähd.al.', 'Sipoonlahden levähdysalue'),
    ('Siren', 'Sirén'),
    ('Terv.', 'Terveys'),
    ('Tv', 'TV'),
    ('Viikinm.', 'Viikinmäen'),
    ('ammattik.', 'ammattikoulu'),
    ('as.', 'asema'),
    ('hautausm', 'hautausmaa'),
    ('huoltol', 'huoltolaituri'),
    ('kesk.', 'keskus'),
    ('la-as.', 'linja-autoasema'),
    ('lab.', 'laboratorio'),
    ('leikkiniitt', 'leikkiniitty'),
    ('matkakesk', 'matkakeskus'),
    ('mk', 'matkakeskus'),
    ('op.', 'opisto'),
    ('opetusp.', 'opetuspiste'),
    ('ostosk.', 'ostoskeskus'),
    ('p', 'polku'),
    ('p.', 'puisto'),
    ('palv.talo', 'palvelutalo'),
    ('palveluk', 'palvelukeskus'),
    ('poh', 'pohjoinen'),
    ('puist.', 'puistikko'),
    ('päälait', 'päälaituri'),
    ('ristey', 'risteys'),
    ('siirt.puutarha', 'siirtolapuutarha'),
    ('t.', 'tie'),
    ('term.', 'terminaali'),
    ('terv.as.', 'terveysasema'),
    ('terv.asema', 'terveysasema'),
    ('terveysas.', 'terveysasema'),
    ('uimah.', 'uimahalli'),
    ('urheiluk.', 'urheilukenttä'),
    ('urheiluk.', 'urheilukeskus'),
    ('vanhaink.', 'vanhainkoti'),
    ('virastot.', 'virastotalo'),
    ('Östersund.', 'Östersundomin'),
]

# Sort to descending length of abbreviation
synonyms.sort(key=lambda x: (len(x[0]), x[1], x[0]), reverse=True)

def get_overpass_area(clist):
    area = "("+ ' '.join(\
      [ 'area[boundary=administrative][admin_level=8][name="{}"][ref={}];'\
        .format(c, city2ref[c]) for c in clist ]) + ")->.hel;"
    return area

overpass_area = get_overpass_area(cities)


def longname2stops(longname):
    # First, replace hyphens in know stop names and split and replace back
    # to get a stop list from HSL longName.
    # Match list from gtfs stops.txt:
    # csvtool namedcol "stop_name" stops.txt | grep -o '.*-[[:upper:]]...' | sort -u | tr '\n' '|'
    pat = "Ala-Malm|Ala-Souk|Ala-Tikk|Etelä-Kask|Etelä-Viin|Helsinki-Vant|Itä-Hakk|Kala-Matt|Kallio-Kuni|Koivu-Mank|Lill-Beng|Meri-Rast|Övre-Juss|Pohjois-Haag|Pohjois-Viin|S-Mark|Stor-Kvis|Stor-Rösi|Taka-Niip|Ukko-Pekk|Vanha-Mank|Vanha-Sten|Ylä-Souk|Yli-Finn|Yli-Juss"
    # Other place names with hyphens
    extrapat="|Pohjois-Nikinmä|Länsi-Pasila|Etelä-Leppäv"
    pat = pat + extrapat
    subf = lambda m: m.group().replace('-', '☺')
    stops = re.sub(pat, subf, longname).split('-')
    stops = [s.replace('☺', '-').strip() for s in stops]
    return stops


def get_stopname(ps):
    """Return stop name composed from 'name' and 'platformCode' fields."""
    pname = ps.get("name", None)
    pplat = ps.get("platformCode", None)
    if pplat and pplat[0].isnumeric():
        pn = "{}, laituri {}".format(pname, pplat)
    else:
        pn = pname
    return pn


def normalize_helsinki_codes(dd, change_code=False):
    """Convert keys of the type 'dddd' in input dict to 'Hdddd'."""
    pattern = re.compile("^[0-9]{4,4}$")
    for r in list(dd.keys()): # need a static copy of the keys
        if pattern.match(r):
            newref = 'H' + r
            if change_code and dd[r].get('code'):
                dd[r]['code'] = newref
            dd[newref] = dd.pop(r)

