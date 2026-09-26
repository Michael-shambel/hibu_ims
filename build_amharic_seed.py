"""Build the shipped Amharic seed dictionary (services/data/amharic_seed.json).

The seed is what makes TITANIC -> ቲታኒክ and STORAGE -> ስቶራጅ instead of the
letter-by-letter ቲታኒጭ / ስቶራገ. Edit the vocabulary below and re-run:

    build_env/Scripts/python.exe build_amharic_seed.py

Documentation of the conversion order is in services/amharic_service.py.
"""
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.amharic_service import _TOKEN, _WORD_CHUNK, _translate_chunk, _translate_word

# ---------------------------------------------------------------------------
# Vocabulary.  Word -> correct Amharic.  This is the AI-curated part: it knows
# both how Ethiopian shops write these names and how English words sound.
# ---------------------------------------------------------------------------
WORDS = {
    # --- units / measures -------------------------------------------------
    "100": "100",  # placeholder, digits are passed through anyway
    "GRAM": "ግራም", "KG": "ኪሎ", "L": "ሊ", "LITER": "ሊትር", "ML": "ሚሊ",
    "SANTIM": "ሳንቲም", "KERKER": "ቀርቀር", "ZERG": "ዘርግ",
    "DOZEN": "ደርዘን", "PACK": "ፓክ", "SET": "ሴት", "PAIR": "ጥንድ",

    # --- product vocabulary ----------------------------------------------
    "LION": "ላዮን", "DIST": "ዲስት", "JORO": "ጆሮ", "DUBEL": "ደብል",
    "SINGLE": "ሲንግል", "STOVE": "ስቶቭ", "STOV": "ስቶቭ", "BOILER": "ቦይለር",
    "STAR": "ስታር", "TITANIC": "ቲታኒክ", "STORAGE": "ስቶራጅ",
    "TECH": "ቴክ", "TECHE": "ቴቼ", "MODEL": "ሞደል", "OVAL": "ኦቫል",
    "GLASS": "ግላስ", "WET": "ዌት", "BIG": "ቢግ", "SMALL": "ስሞል",
    "NEW": "ኒው", "COMPLET": "ኮምፕሌት", "BRIGHT": "ብራይት",
    "CHIPS": "ቺፕስ", "JUICE": "ጁስ", "JUS": "ጁስ", "COFFEE": "ኮፌ",
    "COFFE": "ኮፌ", "TEA": "ሻይ", "BUNA": "ቡና", "BUNNA": "ቡና",
    "LUNCH": "ላንች", "BOX": "ቦክስ", "KICHEN": "ኪችን", "EXPERT": "ኤክስፐርት",
    "COLOR": "ኮለር", "SILVER": "ሲልቨር", "GOLD": "ጎልድ", "CREST": "ክረስት",
    "DUBAI": "ዱባይ", "INDIA": "ኢንዲያ", "DIAMOND": "ዳይመንድ",
    "SANFORD": "ሳንፎርድ", "ROYALEX": "ሮያሌክስ", "LOTUS": "ሎተስ",
    "LOTUSE": "ሎተስ", "ROYAL": "ሮያል", "GRAND": "ግራንድ", "NIMA": "ኒማ",
    "AFRAN": "አፍራን", "SAACHI": "ሳቺ", "HOBBY": "ሆቢ", "ROWAY": "ሮዌይ",
    "BILOR": "ቢሎር", "DALY": "ዳሊ", "CHALA": "ጫላ", "KUZI": "ኩዚ",
    "MATARYA": "ማታሪያ", "MUKAP": "ሙካፕ", "REJIM": "ረጂም", "JOKE": "ጆኬ",
    "TIMATIM": "ቲማቲም", "ZEMBABA": "ዘምባባ", "MAYCA": "ማይቻ",
    "MAYCKA": "ማይካ", "YEQEBE": "የቀበ", "WETET": "ወተት", "TELKU": "ተልኩ",
    "SHENKURT": "ሽንኩርት", "SHINKURT": "ሽንኩርት", "MEKAKELEGNA": "መካከለኛ",
    "ENKULAL": "እንኩላል", "AGAGUL": "አጋጉል", "MEAZEN": "ሜዘን",
    "MAEZEN": "ሜዘን", "M/CHA": "ሜ/ቻ", "WUHA": "ውሃ", "EGER": "እግር",
    "JIB": "ጅብ", "KEBUR": "ክቡር", "ZEBEGNA": "ዘበኛ", "AGDEM": "አግደም",
    "BICHA": "ቢቻ", "NECHE": "ነቸ", "GENDA": "ገንዳ", "ERS": "እርስ",
    "BERS": "በርስ", "QALITY": "ቃሊቲ", "QULITY": "ቃሊቲ", "SINI": "ሲኒ",
    "TENSHU": "ትንሹ", "TINISHU": "ትንሹ", "HE": "ሄ", "HOUSE": "ሃውስ",
    "REST": "ሬስት", "ACLERIC": "አችለሪክ",    "LIMUT": "ልሙት", "LEMUT": "ልሙት",
    "S001": "S001",
    # model / brand codes stay latin so the store reads them as usual
    "ZB": "ZB", "VS": "VS", "GR": "GR", "PA": "PA", "PE": "PE", "PL": "PL",
    "FA": "FA", "EP": "EP", "TR": "TR", "SB": "SB", "MK": "ሚካ", "ATM": "ATM",

    # --- Amharic words used in delivery names ------------------------------
    "TERA": "ተራ", "LE": "ለ", "ADISU": "አዲሱ", "NEBAR": "ነበር",
    "MEGAZEN": "መጋዘን", "GA": "ጋ", "BER": "በር", "MESOB": "መሶብ",
    "MERAB": "ምዕራብ", "MIRAB": "ምዕራብ", "LEJ": "ልጅ", "LIJ": "ልጅ",
    "KUTER": "ቁተር", "QUTER": "ቁተር", "KUTRE": "ቁተር", "KUTR": "ቁተር",
    "KUYR": "ቁተር", "KUT": "ቁተር", "NAZRET": "ናዝረት", "NAZERET": "ናዝረት",
    "NAZERAT": "ናዝረት", "AFYA": "አፍያ", "YEMETAL": "የመታል", "YELEKAL": "የለካል",
    "YELKAL": "የልካል", "TEWEKEL": "ተወከል", "Y": "የ", "M": "ም", "A": "አ",
    "D": "ድ", "B": "ብ", "S": "ስ", "K": "ክ", "W": "ው", "T": "ት",
    "H": "ህ", "N": "ን", "G": "ግ", "O": "ኦ", "C": "ክ", "BE": "በ",
    "SHASHEMENE": "ሻሸመኔ", "SHASHEMNE": "ሻሸመኔ", "SHSHEMNE": "ሻሸመኔ",
    "SHSHEMEN": "ሻሸመኔ", "SHAHEMENE": "ሻሸመኔ", "SHASHENE": "ሻሸመኔ",
    "SHASEMENE": "ሻሸመኔ", "SHASHEME": "ሻሸመኔ", "SHASHMENE": "ሻሸመኔ",
    "KOROKONCH": "ቆሮኮንች", "KOREKONCH": "ቆሮኮንች", "BAHERDAR": "ባህርዳር",
    "BAHRDAR": "ባህርዳር", "BAHARDAR": "ባህርዳር", "BEHARDAR": "ባህርዳር",
    "BAHRDAR,": "ባህርዳር", "AWASA": "አዋሳ", "GOMA": "ጎማ", "GAR": "ጋር",
    "HENTSA": "ሄንጻ", "HENSTA": "ሄንጻ", "HENSA": "ሄንጻ", "SEGA": "ሰጋ",
    "ASELA": "አሴላ", "ABEBA": "አበባ", "BELO": "ቤሎ", "AZEMERAW": "አዘመራው",
    "AZMERAW": "አዘመራው", "TAXI": "ታክሲ", "TAKSI": "ታክሲ", "SEID": "ሰይድ",
    "DEBERE": "ደብረ", "DEBRE": "ደብረ", "DEBER": "ደብረ", "HARER": "ሐረር",
    "HARERE": "ሐረር", "ADIS": "አዲስ", "ADISS": "አዲስ", "TSEHAY": "ጸሐይ",
    "TESHAY": "ጸሐይ", "MARKOS": "ማርቆስ", "MARKOSE": "ማርቆስ",
    "MARQOSE": "ማርቆስ", "MARQOS": "ማርቆስ", "TANA": "ጣና", "ALEM": "ዓለም",
    "SISAY": "ሲሳይ", "RASU": "ራሱ", "RASE": "ራሱ", "SEAT": "ሰዓት",
    "LAY": "ላይ", "YEHID": "የሚሄድ", "SUQ": "ሱቅ", "MERKATO": "መርካቶ",
    "MERKTO": "መርካቶ", "PARKING": "ፓርኪንግ", "MESGID": "መስጊድ",
    "SINEMA": "ሲኒማ", "CINIMA": "ሲኒማ", "POLIS": "ፖሊስ", "BANK": "ባንክ",
    "BET": "ቤት", "FOQ": "ፎቅ", "FOQUE": "ፎቅ", "BERENDA": "በረንዳ",
    "FIT": "ፊት", "FITLEFIT": "ፊት ለፊት", "ATEGEB": "አጠገብ", "YESHI": "የሺ",
    "YELEWUM": "የለውም", "MEHAL": "መሀል", "SEATU": "ሰዓቱ", "GEBETA": "ገበታ",
    "BERMIL": "በርሚል", "PIKUP": "ፒካፕ", "DELALA": "ደላላ", "AZMACH": "አዝማች",
    "DASHEN": "ዳሸን", "ZENA": "ዜና", "ZINET": "ዝነት", "SELAM": "ሰላም",
    "HIWOT": "ህይወት", "TESFA": "ተስፋ", "BEREKET": "በርከት", "GENET": "ገነት",

    # --- frequent names / places in delivery names -------------------------
    "ESMAEL": "እስማኤል", "ESMAEIL": "እስማኤል", "ESMEL": "እስማኤል",
    "JEMAL": "ጀማል", "MEHAMED": "መሐመድ", "MEHAMMED": "መሐመድ",
    "MOHAMED": "መሐመድ", "MUHAMED": "መሐመድ", "MOHAMMED": "መሐመድ",
    "NASER": "ናሰር", "NASIR": "ናሰር", "NASWER": "ናሰር", "ABDI": "አብዲ",
    "ADMAS": "አድማስ", "ADMASE": "አድማስ", "ADEMASE": "አድማስ",
    "ADEMAS": "አድማስ", "ABDUKERIM": "አብዱከሪም", "ABDULKERIM": "አብዱልከሪም",
    "ZEKARYAS": "ዘካርያስ", "ZEKARIYASE": "ዘካርያስ", "EBRAHIM": "ኢብራሂም",
    "IBRAHIM": "ኢብራሂም", "METRO": "ሜትሮ", "HAJI": "ሐጂ", "JIMA": "ጅማ",
    "MUBARIK": "ሙባሪክ", "MUBAREK": "ሙባሪክ", "GONDER": "ጎንደር",
    "DAWUD": "ዳውድ", "DAWED": "ዳውድ", "KAMIL": "ካሚል", "KAMELS": "ካሚል",
    "ZELALEM": "ዘላለም", "FERASH": "ፈራሽ", "MELAKU": "መላኩ",
    "WEYNSHET": "ወይንሸት", "WEYNESHET": "ወይንሸት", "NEGASH": "ነጋሽ",
    "YASIN": "ያሲን", "ABDO": "አብዶ", "CHOREGA": "ጮረጋ", "AFEYA": "አፈያ",
    "FUAD": "ፉአድ", "DANIEL": "ዳንኤል", "DANIE": "ዳንኤል", "ZIYAD": "ዚያድ",
    "HAYMANOT": "ሃይማኖት", "SEMERE": "ሰመረ", "MIFTA": "ሚፍታ",
    "BERHANU": "በርሃኑ", "BERHAN": "በርሃን", "ABDU": "አብዱ", "ABDUL": "አብዱ",
    "BAZAR": "ባዛር", "BOLE": "ቦሌ", "MEKELLE": "መቀለ", "MEKELE": "መቀለ",
    "ASEFA": "አሰፋ", "ABDULWAHID": "አብዱልዋሂድ", "SHEWA": "ሸዋ",
    "UMER": "ኡመር", "OUMER": "ኡመር", "MERKATO": "መርካቶ", "HAYLE": "ሃይሌ",
    "TESFA": "ተስፋ", "ABEL": "አቤል", "GOMEN": "ጎመን", "FANTAHUN": "ፋንታሁን",
    "AMIR": "አሚር", "HASEN": "ሃሰን", "HASAN": "ሃሰን", "HAFTOM": "ሃፍቶም",
    "DANI": "ዳኒ", "DILA": "ዲላ", "ANWAR": "አንዋር", "SHOLA": "ሾላ",
    "AMBESA": "አምበሳ", "TADELE": "ታደለ", "LEWI": "ሌዊ", "ALI": "አሊ",
    "HARUN": "ሃሩን", "FEVEN": "ፌቨን", "NURBEZA": "ኑርበዛ", "NURADIS": "ኑራዲስ",
    "MURID": "ሙሪድ", "SADIQ": "ሳዲቅ", "SADIK": "ሳዲቅ", "ALIF": "አሊፍ",
    "ZEYNU": "ዘይኑ", "ESUBALEW": "እሱባለው", "ABDUSELAM": "አብዱሰላም",
    "ROBE": "ሮቤ", "ROBEA": "ሮቤ", "YESUF": "ዩሱፍ", "YOSEF": "ዮሴፍ",
    "MEZID": "መዚድ", "MUSTEFA": "ሙስተፋ", "MESERET": "መሰረት",
    "BEZA": "ቤዛ", "ROMAN": "ሮማን", "ABDULMEJID": "አብዱልመጂድ",
    "TELAHUN": "ተላሁን", "FARUQ": "ፋሩቅ", "DEREDAWA": "ድሬዳዋ",
    "TEREFE": "ተረፈ", "EZEDIN": "ኢዘዲን", "HAYLEMARYAM": "ሃይለማርያም",
    "LEGESE": "ለገሰ", "TEFERA": "ተፈራ", "KARA": "ካራ", "NEJAT": "ነጃት",
    "NEGATU": "ነጋቱ", "HANA": "ሃና", "ELYAS": "ኤልያስ", "EYASU": "እያሱ",
    "DABO": "ዳቦ", "ABERHAM": "አብርሃም", "ABRAHAM": "አብርሃም",
    "TEMESGEN": "ተመስገን", "TEMSEGEN": "ተመስገን", "METU": "መቱ",
    "YONASE": "ዮናስ", "YONAS": "ዮናስ", "RESHAD": "ሬሻድ", "YASMIN": "ያስሚን",
    "ZEGEYE": "ዘገየ", "BERHE": "በርሄ", "ABDULFETA": "አብዱልፈታ",
    "MEKONEN": "መኮንን", "HABTAMU": "ሀብታሙ", "GASH": "ጋሽ", "GASHAW": "ጋሻው",
    "BELAY": "በላይ", "BELAYNESH": "በላይነሽ", "AZIZA": "አዚዛ", "AZIZ": "አዚዝ",
    "REHIMA": "ረሂማ", "DAWIT": "ዳዊት", "RAS": "ራስ", "EYOB": "ኢዮብ",
    "ENDRIS": "እንድሪስ", "MIKAEL": "ሚካኤል", "MIKEAL": "ሚካኤል",
    "RIHAN": "ሪሃን", "IMAM": "ኢማም", "EIMAM": "ኢማም", "ADAMA": "አዳማ",
    "ABDELA": "አብደላ", "NUR": "ኑር", "NURU": "ኑር", "NURE": "ኑር",
    "HENOK": "ሄኖክ", "EFREM": "ኤፍሬም", "ALMAZ": "አልማዝ", "BAHRU": "ባህሩ",
    "MEQDES": "መቅደስ", "MEKDES": "መቅደስ", "ERMYAS": "ኤርሚያስ",
    "ABUBEKER": "አቡበከር", "AYELE": "አየለ", "TESEMA": "ተሰማ",
    "KASAHUN": "ካሳሁን", "TSEGAYE": "ጸጋዬ", "TEGAYE": "ጸጋዬ", "ATNAFU": "አትናፉ",
    "ZELEKE": "ዘለቀ", "SEYFU": "ሰይፉ", "MULUGETA": "ሙሉጌታ", "EDEN": "ኤደን",
    "MESELE": "መሰለ", "ADANE": "አዳነ", "GETACHEW": "ጌታቸው",
    "ABDUREZAQ": "አብዱረዛቅ", "ASOSA": "አሶሳ", "RIDWAN": "ሪድዋን",
    "KERIMA": "ከሪማ", "KERIM": "ከሪም", "ZEWDU": "ዘውዱ", "MUSA": "ሙሳ",
    "BILAL": "ቢላል", "BAHREDIN": "ባህረዲን", "WENDMU": "ወንድሙ",
    "WENDEMU": "ወንድሙ", "BALTENA": "ባልጠና", "MURAD": "ሙራድ",
    "KELIFA": "ከሊፋ", "FEYSEL": "ፌሰል", "ABDULHAMID": "አብዱልሀሚድ",
    "JIJIGA": "ጅጅጋ", "MESFEN": "መስፍን", "JINKA": "ጂንካ", "HELINA": "ሄሊና",
    "ABUSH": "አቡሽ", "KOMBOLCHA": "ኮምቦልቻ", "KEMISE": "ከሚሴ",
    "ENDALE": "እንዳለ", "AGARO": "አጋሮ", "SEBEHEDIN": "ሰበሀዲን",
    "AMANUEL": "አማኑኤል", "ALEX": "አሌክስ", "ALAMUDIN": "አላሙዲን",
    "ETHIO": "ኢትዮ", "ABDULAZIZ": "አብዱልአዚዝ", "GELELA": "ገሊላ",
    "GELILA": "ገሊላ", "SIDAMO": "ሲዳሞ", "AKSUM": "አክሰም", "TARIKU": "ታሪኩ",
    "SOLOMON": "ሰለሞን", "SIRAJ": "ሲራጅ", "SALIM": "ሳሊም", "WERQU": "ወርቁ",
    "WERQ": "ወርቁ", "REDWAN": "ሪድዋን", "OSMAN": "ኦስማን", "ADABA": "አዳባ",
    "ASHENAFI": "አሸናፊ", "ASFAW": "አስፋው", "MULALEM": "ሙላለም",
    "MERWAN": "መርዋን", "TOLOSA": "ቶሎሳ", "TARE": "ታሬ", "MESFIN": "መስፍን",
    "BESUFKAD": "በሱፍቃድ", "TSEDEY": "ጽደይ", "DAGEM": "ዳግም",
    "ABISSNYA": "አቢሲንያ", "ABISINYA": "አቢሲንያ", "ABISSNA": "አቢሲንያ",
    "ABISNYA": "አቢሲንያ", "HAYREDIN": "ሃይረዲን", "HEYREDIN": "ሃይረዲን",
    "MESHESHA": "መሸሻ", "HOSANA": "ሆሳና", "ARADA": "አራዳ", "KIRKOS": "ቂርቆስ",
    "WEREDA": "ወረዳ", "KEBELE": "ቀበሌ", "GULIT": "ጉሊት", "SHROMEDA": "ሽሮ መዳ",
    "GOTERA": "ጎተራ", "SEFER": "ሰፈር", "WONJI": "ወንጂ", "MOJO": "ሞጆ",
    "DUKEM": "ዱከም", "LEGETAFO": "ለገጣፎ", "SULULTA": "ሱሉልታ", "GELAN": "ገላን",
    "CHANCHO": "ጫንቾ", "WELISO": "ወሊሶ", "BUQQA": "ቡቃ", "GERJI": "ገርጂ",
    "MEGENAGNA": "መገናኛ", "KALITY": "ቃሊቲ", "SARIS": "ሳሪስ", "HAILE": "ሃይሌ",
    "GARMENT": "ጋርመንት", "MERI": "መሪ", "MIZAN": "ሚዛን", "TEPI": "ቴፒ",
    "METEHARA": "መተሀራ", "HAWASSA": "ሀዋሳ", "BISHOFTU": "ቢሾፍቱ",
    "TEKLEHAYMANOT": "ተክለሃይማኖት", "TEKLHAYMANOT": "ተክለሃይማኖት",
    "T/HAYMANOT": "ተ/ሃይማኖት", "KALID": "ካሊድ", "MUDIN": "ሙዲን",
    "KASIM": "ካሲም", "QASIM": "ካሲም", "ABEBE": "አበበ", "AREGA": "አረጋ",
    "FEREJA": "ፈረጃ", "KEMAL": "ከማል", "DAR": "ዳር", "ADEM": "አደም",
    "MUAZ": "ሙአዝ", "DESE": "ደሴ", "DESIE": "ደሴ",
    "DEBREMARQOS": "ደብረ ማርቆስ", "HUSEN": "ሁሴን", "AHMED": "አህመድ",
    "HEYERDIN": "ሃይረዲን", "YE": "የ", "ASKO": "አስኮ",
    "M/TERA": "መ/ተራ", "Y/MEMECH": "የ/መመች", "B/DAR": "ባ/ዳር",
    "A/NEBAR": "አ/ነበር", "A/HENTSA": "አ/ሄንጻ", "D/MARQOS": "ደ/ማርቆስ",
    # best guess, flagged for review in the dialog
    "KEDER": "ቀደር", "SHERA": "ሸራ", "BERET": "በረት", "HADERE": "ሃደረ",
    "DAMEJ": "ዳመጅ", "MEMECH": "መመች", "JEWAR": "ጄዋር",
    "KEMER": "ከመር", "RAGUEL": "ራጉኤል", "QEMER": "ቀመር", "TEBLO": "ጠብሎ",
    "BERUK": "ብሩክ",
}

# ---------------------------------------------------------------------------
# Words that follow the English rewrite rules (they are not Amharic words).
# ---------------------------------------------------------------------------
ENGLISH = {
    "TITANIC", "STORAGE", "CHIPS", "JUICE", "JUS", "COFFEE", "COFFE", "TEA",
    "STOVE", "STOV", "BOILER", "GLASS", "KICHEN", "EXPERT", "LUNCH", "BOX",
    "MODEL", "SILVER", "GOLD", "COLOR", "COMPLET", "BRIGHT", "GRAND",
    "SANFORD", "ROYALEX", "ROYAL", "DUBAI", "INDIA", "DIAMOND", "LOTUS",
    "SINGLE", "DUBEL", "TECH", "TECHE", "NEW", "BIG", "SMALL", "STAR",
    "HOTEL", "CAFE", "SHOP", "STORE", "MARKET", "CENTER", "PLASTIC", "STEEL",
    "IRON", "METAL", "WOODEN", "PAPER", "BOTTLE", "WATER", "PUMP", "MOTOR",
    "MACHINE", "SPARE", "PART", "PARTY", "CLASSIC", "SUPER", "PERFECT",
    "PRIME", "QUALITY", "ROYAL", "CROWN", "ELEGANT", "MODERN", "STANDARD",
    "DELUXE", "PREMIUM", "SPECIAL", "ORIGINAL", "SMART", "PRACTICAL",
}

# ---------------------------------------------------------------------------
# Low-confidence entries: the dialog flags any name containing these.
# ---------------------------------------------------------------------------
REVIEW = {
    "KERKER", "ZERG", "MEAZEN", "MAEZEN", "M/CHA", "DALY", "MATARYA",
    "MUKAP", "MAYCA", "MAYCKA", "YEQEBE", "TELKU", "ACLERIC", "LIMUT",
    "LEMUT", "HE", "BICHA", "NECHE", "AGDEM", "BILOR", "AFYA", "YEMETAL",
    "KEDER", "HENTSA", "SHERA", "SHORTI", "BELO", "HADERE", "DAMEJ", "MEMECH",
    "TEQEMEMECH", "YTEQEMEMECH", "YETEQEMEMECH", "YETKMEMEMECH", "YETKMEMECH",
    "YETKEMEMECH", "YETEKEMEMECH", "CHID", "CHED", "RAEY", "SHIGAZ", "MASHO",
    "LEFIT", "TSEDEY", "TECHE", "CHALA", "KUZI", "JOKE", "GOLD", "TEA",
    "WETET", "TELKU", "HELUF", "BERUK", "KEDRE", "SEADA", "MULE",
    "B/DAR", "A/NEBAR", "A/HENTSA", "D/MARQOS", "Y/MEMECH", "M/TERA",
}


def compose(name, entries, english):
    """Compose a full name from the word table + rules (same as the service)."""
    out = []
    for token in _TOKEN.findall(name):
        if _WORD_CHUNK.fullmatch(token) is None:
            out.append(token)
        else:
            out.append(_translate_chunk(token, entries, english))
    return "".join(out)


# Names whose composed form needs a human decision (unit spelling, codes).
EXACT = {
    "6 L KICHEN EXPERT": "6 ሊትር ኪችን ኤክስፐርት",
    "AFRAN 6L": "አፍራን 6 ሊትር",
    "HE HOUSE 6L": "ሄ ሃውስ 6 ሊትር",
    "GRAND NIMA COFFEM3": "ግራንድ ኒማ ኮፌም3",
    "GRAND NIMA COFFE (NEW )": "ግራንድ ኒማ ኮፌ (ኒው)",
    "GOLD REST  TECH 2": "ጎልድ ሬስት ቴክ 2",
}


SEED_PATH = os.path.join("services", "data", "amharic_seed.json")


def read_catalogue(db_path="database/inventory.db"):
    """Product names from the live database; an empty catalogue is an error."""
    if not os.path.exists(db_path):
        raise SystemExit(
            f"❌ {db_path} not found.\n"
            "   This tool runs against the shop's real database: it needs the "
            "product\n   catalogue to give every product an exact Amharic name. "
            "Nothing was\n   written, the existing seed was kept. Run it on the "
            "machine that has the data.")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        products = sorted({r[0].strip() for r in conn.execute(
            "select name from professional_products where is_deleted=0") if r[0]})
    finally:
        conn.close()
    if not products:
        raise SystemExit(
            "❌ the database has no products (fresh / empty install).\n"
            "   Writing the seed now would drop the product names, so nothing "
            "was\n   changed. The shipped seed already covers the vocabulary, "
            "and any new\n   product is converted by the rules until someone "
            "fixes it in\n   Reports -> 🇪🇹 Amharic Names.")
    return products


def main():
    entries = dict(WORDS)
    products = read_catalogue()
    names = {}
    for name in products:
        if not name:
            continue
        upper = name.upper()
        names[upper] = EXACT.get(upper) or compose(name, entries, ENGLISH)

    seed = {
        "version": 1,
        "generated": "2026-09-23",
        "source": "AI-curated transliteration for the names used by Megazen IMS",
        "entries": {**entries, **names},
        "english": sorted(ENGLISH),
        "review": sorted(REVIEW),
    }
    path = SEED_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(seed, handle, ensure_ascii=False, indent=1, sort_keys=True)

    print(f"seed written: {len(entries)} words + {len(names)} product names")
    print()
    for name in products:
        print(f"  {name:38s} -> {names.get(name.upper(), '?')}")


if __name__ == "__main__":
    main()
