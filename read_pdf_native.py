import anthropic
import base64
import json

client = anthropic.Anthropic()

# ─────────────────────────────────────────────────────────────
# STEP 1: Read the PDF file and encode it for transmission.
# APIs send data as text (JSON), but a PDF is binary data — so we
# convert it into base64, a text-safe encoding, before sending.
# "rb" means "read binary" — necessary for a PDF, unlike a normal
# text file which you'd open with just "r".
# ─────────────────────────────────────────────────────────────
with open("paper8_aboatia_CoNi_tailings.pdf", "rb") as f:
    pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

# ─────────────────────────────────────────────────────────────
# STEP 2: Your existing extraction prompt — UNCHANGED from extract.py.
# ─────────────────────────────────────────────────────────────
extraction_prompt = """
You are a data extraction engine for liquid-liquid extraction (LLE) research.
Your task is to read a scientific paper on solvent extraction of metals and
extract every reported experimental data point into structured JSON.

You are NOT summarising. You are NOT interpreting. You extract only what is
literally stated in the paper.

RULES:
1. ONE DATA POINT PER RECORD. A "data point" is one metal measured under one
   specific set of conditions. A table with 3 metals x 2 stages = 6 records.
   If a table reports both a raffinate measurement AND an extract measurement
   for the same metal, and they were taken at different equilibrium pH values
   or different process stages, these are TWO separate records, not one -
   never merge two measurements into a single record if it would require
   dropping one of their reported values.
2. NEVER GUESS. If a value is not stated, write "N.R." (not reported).
3. DO NOT CALCULATE. If raw concentrations are given (feed, raffinate,
   extract) but D or %E are not explicitly stated, record the raw
   concentrations and set D and %E to "N.R." Never derive one metric from
   another, even if the numbers needed are present.
4. DISTINGUISH initial_pH (set before extraction) from equilibrium_pH
   (measured after/during extraction, e.g. "pH_avg" or "Eq. pH" in tables).
   If a paper only reports an operating/average pH during the process with
   no clear pre-extraction initial pH, set initial_pH to "N.R." and use
   equilibrium_pH for the reported value.
5. COMBINE DATA ACROSS THE PAPER - conditions, results, and feed
   concentrations may be in different tables or sections.
6. initial_metal_concentration is the feed concentration of THAT record's
   metal specifically, not the whole solution. ONLY create records for
   these five target metals: Co, Ni, Mn, Li, Cu. Do not create records
   for other reported species (e.g. Na, background salts, impurities),
   even if they are extracted or measured.
7. Read the methods section carefully for modifiers - different extractants
   in the SAME paper may have different modifiers (or none). Do not assume
   consistency; check what is stated for each specific extractant system.
8. SEPARATION FACTOR IS PAIRWISE. If the paper reports a separation factor
   or "log separation factor" between the target metal and one or more
   other metals, create ONE ADDITIONAL RECORD PER PAIR: target_metal stays
   the primary metal, reference_metal is the metal it is compared against,
   separation_factor_beta is the reported value, and separation_factor_scale
   states whether it is "linear" or "log" exactly as the paper describes it.
   Never convert between linear and log scale yourself.
9. MERGE SAME-EXPERIMENT DATA ACROSS SECTIONS. If two different parts of the
   paper (e.g. a summary sentence and a later detailed methods paragraph)
   clearly describe the SAME experiment - same extractant, same target metal,
   same stated conditions - combine them into ONE complete record rather than
   creating separate partial records for each section. Only split into
   multiple records when the underlying experiments are genuinely different
   (different stage, different pH, different concentration, etc.).
10. BASELINE CONCENTRATION RECORDS ARE INDEPENDENT OF SEPARATION FACTOR
    RECORDS. If a table or figure reports the feed concentration of a metal,
    create a baseline record for that metal (target_metal = that metal,
    initial_metal_concentration = the reported value, all extraction-specific
    fields "N.R.") REGARDLESS of whether that same metal also appears as a
    reference_metal in a separation factor record elsewhere. These are two
    different pieces of information about the same metal and BOTH must be
    captured, never one instead of the other.
11. Capture contact_time_min, settling_time_min, and stage_number whenever
    explicitly stated, in addition to all existing fields. These often
    appear in table captions alongside pH and temperature, e.g. "reaction
    time: 30 min" or "stage 1 of 2".

FIELDS TO EXTRACT (for each record):
source_doi, source_location, target_metal, extractant,
extractant_concentration, diluent, modifier, initial_pH, equilibrium_pH,
phase_ratio_OA, initial_metal_concentration, aqueous_concentration_after,
organic_concentration_extract, temperature_C, contact_time_min,
settling_time_min, stage_number, extraction_efficiency_pctE,
distribution_ratio_D, separation_factor_beta, reference_metal,
separation_factor_scale, analytical_method

WORKED EXAMPLE:
If the paper contained:
  [Methods] "Commercial grade kerosene was employed as a diluent."
  [Table 1] Feed: Co(II) 1869 mg/L, Mn(II) 258 mg/L, Ni(II) 9258 mg/L
  [Table 2 caption] "...30% saponified 0.3 M Cyanex 272 at unity phase
  ratio. (Initial pH: 6, temperature: 25C, reaction time: 30min)"
  [Table 2] stage 1: Mn 88.4, Co 97.2, Ni 2.3, Eq. pH 4.77

Then the Co(II) record would be:
{
  "source_doi": "10.5277/ppmp/193742",
  "source_location": "Table 2, stage 1",
  "target_metal": "Co",
  "extractant": "Cyanex 272 (30% saponified)",
  "extractant_concentration": "0.3 mol/L",
  "diluent": "kerosene",
  "modifier": "N.R.",
  "initial_pH": 6,
  "equilibrium_pH": 4.77,
  "phase_ratio_OA": "1:1",
  "initial_metal_concentration": "1869 mg/L",
  "aqueous_concentration_after": "N.R.",
  "organic_concentration_extract": "N.R.",
  "temperature_C": 25,
  "contact_time_min": 30,
  "settling_time_min": "N.R.",
  "stage_number": 1,
  "extraction_efficiency_pctE": 97.2,
  "distribution_ratio_D": "N.R.",
  "separation_factor_beta": "N.R.",
  "reference_metal": "N.R.",
  "separation_factor_scale": "N.R.",
  "analytical_method": "N.R."
}

OUTPUT FORMAT:
Return a JSON array of records: [ {record1}, {record2}, ... ]
Return ONLY the JSON. No preamble, no explanation, no markdown fences.
"""

# ─────────────────────────────────────────────────────────────
# STEP 3: Send the PDF document + the prompt together in one request.
# ─────────────────────────────────────────────────────────────
with client.messages.stream(
    model="claude-sonnet-4-5-20250929",
    max_tokens=24000,
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_data
                    }
                },
                {
                    "type": "text",
                    "text": extraction_prompt
                }
            ]
        }
    ]
) as stream:
    for text in stream.text_stream:
        pass  # we don't need to print live, just let it accumulate
    response = stream.get_final_message()
print(f"Stop reason: {response.stop_reason}")
raw_output = response.content[0].text


cleaned_output = raw_output.strip()
if cleaned_output.startswith("```"):
    cleaned_output = cleaned_output.strip("`")
    cleaned_output = cleaned_output.replace("json", "", 1).strip()

try:
    records = json.loads(cleaned_output)
except json.JSONDecodeError:
    print("ERROR: could not parse as JSON. Raw output below:\n")
    print(cleaned_output)
    raise

with open("extracted_data_paper8.json", "w") as f:
    json.dump(records, f, indent=2)

print(f"Extracted {len(records)} records.\n")
for r in records:
    print(r)