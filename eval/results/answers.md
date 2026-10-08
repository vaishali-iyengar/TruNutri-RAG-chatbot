# Answer check (6.8)

Model: `openai/gpt-oss-120b` on Groq. Questions: 27. LLM cache: 27 hits, 0 calls.

| Measure | Value |
|---|---|
| Blend rate in rendered answers | 0/102 claims |
| Claims the model proposed citing another document | 0 |
| Status | answered 26, partial 1 |
| Claims dropped by the validator | 0 (none) |
| Rendered claims | 102 |
| Time per question (median / max, incl. retrieval) | 0.9 s / 5.9 s |

## Answers with their cited text

### sd-01 (single_doc): What does WHO recommend about daily salt intake?

**Status:** answered

**Expected (golden notes):** In adults, salt intake should be limited to less than 5 grams per day (2 grams per day sodium); for children the maximum is lower and estimated from energy intake.

**who-healthy-diet**
- In adults, salt intake should be limited to less than 5 grams per day (2 grams per day sodium).
    - `who-healthy-diet:salt-sodium-and-potassium:2`: - In many countries, most salt comes from processed foods (e.g. ready meals; processed meats such as bacon, ham and salami; cheese; and salty snacks) or from foods consumed frequently in large amounts (e.g. bread). Salt is also added to foods during cooking (e.g. bouillon, stock cubes, soy sauce and fish sauce) or at the point of consumption (e.g. table salt). - In adults, salt intake should be li…

### sd-02 (single_doc): How much fruit and vegetables does WHO recommend eating each day?

**Status:** answered

**Expected (golden notes):** Everyone older than 10 should aim for at least 400 g of fruits and vegetables per day; at least 250 g for children aged 2–5 and 350 g for children aged 6–9.

**who-healthy-diet**
- People older than 10 years should aim for at least 400 g of fruits and vegetables per day.
    - `who-healthy-diet:carbohydrates:1`: Carbohydrates provide the primary energy source for the body. The amount of carbohydrate in the diet can vary and although low and very low carbohydrate diets are used to treat certain conditions, for most people a variety of unrefined carbohydrates should represent a significant portion of the diet, approximately 45–75% of total daily energy. - Carbohydrates in the diet should come primarily from…
- Children 2–5 years should aim for at least 250 g of fruits and vegetables per day.
    - `who-healthy-diet:carbohydrates:1`: Carbohydrates provide the primary energy source for the body. The amount of carbohydrate in the diet can vary and although low and very low carbohydrate diets are used to treat certain conditions, for most people a variety of unrefined carbohydrates should represent a significant portion of the diet, approximately 45–75% of total daily energy. - Carbohydrates in the diet should come primarily from…
- Children 6–9 years should aim for at least 350 g of fruits and vegetables per day.
    - `who-healthy-diet:carbohydrates:1`: Carbohydrates provide the primary energy source for the body. The amount of carbohydrate in the diet can vary and although low and very low carbohydrate diets are used to treat certain conditions, for most people a variety of unrefined carbohydrates should represent a significant portion of the diet, approximately 45–75% of total daily energy. - Carbohydrates in the diet should come primarily from…

### sd-03 (single_doc): What health and hygiene requirements apply to people who handle milk and milk products?

**Status:** answered

**Expected (golden notes):** Handlers need a medical examination by a registered medical practitioner before joining and then annually; people with jaundice, diarrhoea, vomiting, fever, infected lesions etc. are excluded from handling; cuts must be covered; hand-washing facilities with soap must be provided (p. 16, 47).

**fssai-fsms-milk**
- Milk and milk product handlers must undergo a medical examination by a registered medical practitioner before joining and annually thereafter to ensure they are free from infectious or communicable diseases.
    - `fssai-fsms-milk:1-health-status-and-illness-injury:1`: i. Milk and milk product handlers of the manufacturing facility shall undergo a medical examination by a registered medical practitioner before joining for work and thereafter annually to ensure that they are free from any infectious or communicable diseases. A record of these examinations shall be maintained. ii. The employees in manufacturing units shall be inoculated against the enteric group o…
- Handlers must be inoculated against the enteric group of diseases as per the recommended vaccine schedule and records must be maintained.
    - `fssai-fsms-milk:1-health-status-and-illness-injury:1`: i. Milk and milk product handlers of the manufacturing facility shall undergo a medical examination by a registered medical practitioner before joining for work and thereafter annually to ensure that they are free from any infectious or communicable diseases. A record of these examinations shall be maintained. ii. The employees in manufacturing units shall be inoculated against the enteric group o…
- Personnel known or suspected to be carriers of a disease likely transmissible through milk must be prevented from handling milk or related materials until they obtain a fit‑to‑work certificate from a registered medical practitioner.
    - `fssai-fsms-milk:1-health-status-and-illness-injury:1`: i. Milk and milk product handlers of the manufacturing facility shall undergo a medical examination by a registered medical practitioner before joining for work and thereafter annually to ensure that they are free from any infectious or communicable diseases. A record of these examinations shall be maintained. ii. The employees in manufacturing units shall be inoculated against the enteric group o…
- Handlers must report conditions such as jaundice, diarrhoea, vomiting, fever, sore throat with fever, infected lesions, or discharges, and any open cuts, wounds or burns must be covered with suitable waterproof dressings before work.
    - `fssai-fsms-milk:1-health-status-and-illness-injury:1`: i. Milk and milk product handlers of the manufacturing facility shall undergo a medical examination by a registered medical practitioner before joining for work and thereafter annually to ensure that they are free from any infectious or communicable diseases. A record of these examinations shall be maintained. ii. The employees in manufacturing units shall be inoculated against the enteric group o…
- An effective personal hygiene programme must be implemented, prohibiting unhygienic practices such as smoking, chewing, eating, sneezing or coughing over unprotected food, spitting, and personal effects like jewellery, watches, pins or perfumes must not be worn in food handling areas.
    - `fssai-fsms-milk:3-personal-behaviour:1`: i. The Milk and milk product manufacturer shall implement an effective personal hygiene programme that identifies hygienic behaviour and habits to be followed by personnel to prevent contamination of food. ii. Any behaviour or unhygienic practices which could result in contamination of Milk and milk product shall be prohibited in food processing, distribution, storage and handling areas. This incl…
- Personnel must wear clean, fit‑for‑purpose work clothing that provides adequate coverage, has no buttons or pockets above waist level, is laundered at predefined intervals, and hair, beards and moustaches must be fully restrained; appropriate PPE such as aprons, gloves, headgear and shoe covers must be used and maintained hygienically.
    - `fssai-fsms-milk:4-work-wear-and-grooming:1`: i. Personnel who work in, or enter into, areas where exposed products and/or materials are handled shall wear work clothing that is fit for purpose, clean and in good condition (e.g. free from rips, tears or fraying material). ii. Clothing mandated for Milk and milk product protection or hygiene purposes shall not be used for any other purpose. iii. Work wear shall not have buttons and outside poc…
    - `fssai-fsms-milk:e-inspection-checklist:3`: - 39 Effluent Treatment Plant (ETP) is in place. Disposal of sewage and effluents is done in conformity with standards laid down under Environment 2 - 40 Protection Act, 1986. IV Personal Hygiene - 41 Annual medical examination & inoculation of food handlers against the enteric group of diseases as per 2 recommended schedule of the vaccine is done. Check for records. - 42 No person suffering from …

### sd-04 (single_doc): How should fresh fruits and vegetables be washed during processing?

**Status:** answered

**Expected (golden notes):** Fruits and vegetables should be washed as needed to remove soil or other contamination; water used for washing, rinsing or conveying final products must be of potable quality; cleaned and sanitised produce is stored separately from untreated produce (p. 37).

**fssai-fsms-fruits-vegetables**
- Fruits and vegetables should be washed as needed to remove soil or other contamination.
    - `fssai-fsms-fruits-vegetables:2-4-hygiene-control-in-specific-process-steps:1`: Preparatory operations leading to the finished product and the packaging operations should be so timed as to permit expeditious handling of consecutive units in production under conditions which would prevent contamination, deterioration, spoilage, or the development of pathogenic or toxicogenic microorganisms. The processing methods should ensure compliance to the relevant standard. - Sorting & G…
- Water used for washing, rinsing, or conveying final food products should be of potable quality.
    - `fssai-fsms-fruits-vegetables:2-4-hygiene-control-in-specific-process-steps:1`: Preparatory operations leading to the finished product and the packaging operations should be so timed as to permit expeditious handling of consecutive units in production under conditions which would prevent contamination, deterioration, spoilage, or the development of pathogenic or toxicogenic microorganisms. The processing methods should ensure compliance to the relevant standard. - Sorting & G…
- Washing may be done with potable water, ozonated water, or chlorinated water.
    - `fssai-fsms-fruits-vegetables:2-4-hygiene-control-in-specific-process-steps:2`: Same equipment should not be used for both treated and untreated products without adequate cleaning and disinfection before use with treated products. - Pre-treatment for minimally processed Fruits & Vegetables: Disinfection is one of the most critical processing steps in fresh-cut fruits and vegetable production. Washing need to be designed to remove dirt, dust and reduce microorganisms, whereas,…

### sd-05 (single_doc): What did JECFA conclude about dietary exposure to adipic acid?

**Status:** answered

**Expected (golden notes):** The group ADI for adipic acid and its salts is 0–5 mg/kg body weight; the Committee concluded that most of its conservative dietary exposure estimates greatly exceed this ADI (by up to ~8000% for high exposures under one scenario) (p. 17–19).

**jecfa-trs-1058**
- The Committee concluded that most conservative dietary exposure estimates greatly exceed the current group ADI of 0–5 mg/kg bw.
    - `jecfa-trs-1058:3-1-1-adipates:5`: The Committee noted that the estimates of dietary exposure calculated at the current meeting are overestimated for a number of reasons, including: the large number of food categories included; the magnitude of the concentrations; the assumption of maximum permitted levels, or the upper end of the range of reported use levels in the food categories; and the assumption that all foods that could cont…
- For the GSFA current maximum levels scenario, high exposures for children exceed the group ADI by up to 660%.
    - `jecfa-trs-1058:3-1-1-adipates:5`: The Committee noted that the estimates of dietary exposure calculated at the current meeting are overestimated for a number of reasons, including: the large number of food categories included; the magnitude of the concentrations; the assumption of maximum permitted levels, or the upper end of the range of reported use levels in the food categories; and the assumption that all foods that could cont…
- For the GSFA current and proposed maximum levels scenario, high exposures for children and adults exceed the group ADI by up to around 8000%.
    - `jecfa-trs-1058:3-1-1-adipates:5`: The Committee noted that the estimates of dietary exposure calculated at the current meeting are overestimated for a number of reasons, including: the large number of food categories included; the magnitude of the concentrations; the assumption of maximum permitted levels, or the upper end of the range of reported use levels in the food categories; and the assumption that all foods that could cont…
- For the use levels scenario, high exposures for children and adults exceed the group ADI by up to 3000%.
    - `jecfa-trs-1058:3-1-1-adipates:5`: The Committee noted that the estimates of dietary exposure calculated at the current meeting are overestimated for a number of reasons, including: the large number of food categories included; the magnitude of the concentrations; the assumption of maximum permitted levels, or the upper end of the range of reported use levels in the food categories; and the assumption that all foods that could cont…
- The Committee calculated high dietary exposure estimates up to 33 mg/kg bw per day for children and up to 4 mg/kg bw per day for adults under the GSFA current maximum levels scenario.
    - `jecfa-trs-1058:3-1-1-adipates:4`: 0.03–16 0.06–33 0.0006–2 0.001–4 1.5–205 3.0–410 0.3–152 0.6–304 0.2–78 0.4–155 0.1–27 0.2–53 a Children included age groups up to 14 or 17 years; adults included age groups from 15 or 18 years. High exposure is mean × 2, approximating the 90th percentile (8). - 2 Some minor errors were identified after the meeting; these were corrected during the editing process with the approval of the Committee…
- Under the GSFA current and proposed maximum levels scenario and the use levels scenario, high dietary exposures were up to 410 mg/kg bw per day for children and up to 304 mg/kg bw per day for adults.
    - `jecfa-trs-1058:3-1-1-adipates:4`: 0.03–16 0.06–33 0.0006–2 0.001–4 1.5–205 3.0–410 0.3–152 0.6–304 0.2–78 0.4–155 0.1–27 0.2–53 a Children included age groups up to 14 or 17 years; adults included age groups from 15 or 18 years. High exposure is mean × 2, approximating the 90th percentile (8). - 2 Some minor errors were identified after the meeting; these were corrected during the editing process with the approval of the Committee…

### tl-01 (table_lookup): How long can raw eggs in the shell be kept in the refrigerator?

**Status:** answered

**Expected (golden notes):** 3 to 5 weeks refrigerated; do not freeze in the shell (beat yolks and whites together, then freeze).

**foodsafety-cold-storage**
- Raw eggs in shell can be kept 3 to 5 weeks in the refrigerator.
    - `foodsafety-cold-storage:cold-food-storage-chart:4`: Table: Cold Food Storage Chart | Food | Type | Refrigerator [40°F (4°C) or below] | Freezer [0°F (-18°C) or below] | |---|---|---|---| | Shellfish | Fresh Crab Meat | 2 - 4 Days | 2 - 4 Months | | Shellfish | Fresh Lobster | 2 - 4 Days | 2 - 4 Months | | Shellfish | Live Crab, Lobster | 1 day . | Not recommended | | Shellfish | Live Clams, Mussels, Oysters, and Scallops | 5 - 10 Days | Not recomme…

### tl-02 (table_lookup): How long do cooked chicken leftovers last in the fridge?

**Status:** answered

**Expected (golden notes):** Leftovers — cooked meat or poultry keep 3 to 4 days in the refrigerator (2 to 6 months frozen).

**foodsafety-cold-storage**
- Cooked meat or poultry leftovers last 3 to 4 days in the refrigerator (40°F/4°C or below).
    - `foodsafety-cold-storage:cold-food-storage-chart:5`: Table: Cold Food Storage Chart | Food | Type | Refrigerator [40°F (4°C) or below] | Freezer [0°F (-18°C) or below] | |---|---|---|---| | Soups and stews | Vegetable or meat added | 3 to 4 days | 2 to 3 months | | Leftovers | Cooked meat or poultry | 3 to 4 days | 2 to 6 months | | Leftovers | Chicken nuggets or patties | 3 to 4 days | 1 to 3 months | | Leftovers | Pizza | 3 to 4 days | 1 to 2 mont…

### tl-03 (table_lookup): How long can raw ground beef be stored in the freezer?

**Status:** answered

**Expected (golden notes):** Hamburger and ground meats keep 3 to 4 months in the freezer (1 to 2 days in the refrigerator).

**foodsafety-cold-storage**
- Ground beef can be stored in the freezer for 3 to 4 months.
    - `foodsafety-cold-storage:cold-food-storage-chart:2`: Table: Cold Food Storage Chart | Food | Type | Refrigerator [40°F (4°C) or below] | Freezer [0°F (-18°C) or below] | |---|---|---|---| | Salad | Egg, chicken, ham, tuna, and macaroni salads | 3 to 4 days | Does not freeze well | | Hot dogs | Opened package | 1 week | 1 to 2 months | | Hot dogs | Unopened package | 2 weeks | 1 to 2 months | | Luncheon meat | Opened package or deli sliced | 3 to 5 d…

### tl-04 (table_lookup): How long does opened deli or luncheon meat keep in the refrigerator?

**Status:** answered

**Expected (golden notes):** Opened package or deli sliced luncheon meat keeps 3 to 5 days refrigerated, 1 to 2 months frozen.

**foodsafety-cold-storage**
- Opened package or deli sliced luncheon meat keeps 3 to 5 days in the refrigerator (40°F (4°C) or below).
    - `foodsafety-cold-storage:cold-food-storage-chart:2`: Table: Cold Food Storage Chart | Food | Type | Refrigerator [40°F (4°C) or below] | Freezer [0°F (-18°C) or below] | |---|---|---|---| | Salad | Egg, chicken, ham, tuna, and macaroni salads | 3 to 4 days | Does not freeze well | | Hot dogs | Opened package | 1 week | 1 to 2 months | | Hot dogs | Unopened package | 2 weeks | 1 to 2 months | | Luncheon meat | Opened package or deli sliced | 3 to 5 d…

### rc-01 (recommendation): What is the Indian dietary guideline on salt?

**Status:** answered

**Expected (golden notes):** Guideline 11 "Restrict salt intake": no more than 5 g of salt (about 1 teaspoon, ~2 g sodium) per day; high salt intake is associated with high blood pressure, heart disease and stomach cancer (p. 90–91). The whole guideline should be retrieved as one chunk.

**icmr-nin-dgi-2024**
- Restrict the intake of added salt (sodium chloride) to a maximum of 5 g per day.
    - `icmr-nin-dgi-2024:are-other-varieties-of-salt-any-better:2`: POINTS TO REGISTER · Use iodized salt · Restrict the intake of added salt (sodium chloride) to a maximum of 5g per day. · Develop a taste for foods/diets that are low in salt from an early age. · Restrict intake of processed and preserved foods such as snack foods, sauces, ketchup, biscuits, chips, cheese and salted fish. · Eat plenty of vegetables and fruits. These are good sources of potassium, …
- Use iodized salt.
    - `icmr-nin-dgi-2024:are-other-varieties-of-salt-any-better:2`: POINTS TO REGISTER · Use iodized salt · Restrict the intake of added salt (sodium chloride) to a maximum of 5g per day. · Develop a taste for foods/diets that are low in salt from an early age. · Restrict intake of processed and preserved foods such as snack foods, sauces, ketchup, biscuits, chips, cheese and salted fish. · Eat plenty of vegetables and fruits. These are good sources of potassium, …
- Develop a taste for foods/diets that are low in salt from an early age.
    - `icmr-nin-dgi-2024:are-other-varieties-of-salt-any-better:2`: POINTS TO REGISTER · Use iodized salt · Restrict the intake of added salt (sodium chloride) to a maximum of 5g per day. · Develop a taste for foods/diets that are low in salt from an early age. · Restrict intake of processed and preserved foods such as snack foods, sauces, ketchup, biscuits, chips, cheese and salted fish. · Eat plenty of vegetables and fruits. These are good sources of potassium, …
- Restrict intake of processed and preserved foods such as snack foods, sauces, ketchup, biscuits, chips, cheese and salted fish.
    - `icmr-nin-dgi-2024:are-other-varieties-of-salt-any-better:2`: POINTS TO REGISTER · Use iodized salt · Restrict the intake of added salt (sodium chloride) to a maximum of 5g per day. · Develop a taste for foods/diets that are low in salt from an early age. · Restrict intake of processed and preserved foods such as snack foods, sauces, ketchup, biscuits, chips, cheese and salted fish. · Eat plenty of vegetables and fruits. These are good sources of potassium, …
- Salt intake in our population generally exceeds the requirement and should not be more than 5 g per day.
    - `icmr-nin-dgi-2024:high-bp-leads-to:1`: intakes. The amount of salt consumed is reflected in urinary sodium levels. Restriction of dietary salt decreases the risk of hypertension. Potassium-rich foods such as fresh vegetables and fruits decrease blood pressure. In fact, it is the ratio of sodium to potassium in the diet which is important. Besides increasing blood pressure, excessive salt may also affect stomach mucosa and increase the …
- Prevalence of hypertension is low in populations consuming less than 3 g salt per day.
    - `icmr-nin-dgi-2024:how-do-sodium-and-potassium-interact-in-the-body:2`: What are the health problems associated with excessive salt/ sodium intake? Existing evidence reveals a deleterious impact of high salt intake on blood vessels, blood pressure, bones and gastrointestinal tract. There is a strong association between salt intake and blood pressure. Prevalence of hypertension is low in populations consuming less than 3g salt per day. The usual increase in blood press…

### rc-02 (recommendation): What does the Dietary Guidelines for Indians recommend about physical activity?

**Status:** answered

**Expected (golden notes):** Guideline 10 "Be physically active and exercise regularly": adults 30–60 minutes of moderate activity a day on at least five days a week (or 15 minutes vigorous); children 60 minutes a day; a minimum 30–45 minute brisk walk helps maintain good health (p. 87–89).

**icmr-nin-dgi-2024**
- Leisure time physical activity such as yoga postures, walking, gardening, dancing etc. is recommended for 60 minutes per day.
    - `icmr-nin-dgi-2024:guidelines-for-physical-activity:2`: Table 10.1. Recommended Physical Activity: Duration for good health | Activity | Duration (min.) | | Sleep | 480 | | Occupation (work) | 480 | | Household chores (cleaning, cooking or washing utensils) | 220 | | Personal care / eating / watching TV | 180 | | Leisure time physical activity (different yoga postures, walking, gardening, dancing etc.) | 60 | | Aerobic exercise (brisk walking, running,…
- Aerobic exercise such as brisk walking, running, swimming, cycling etc. is recommended for 20 minutes per day.
    - `icmr-nin-dgi-2024:guidelines-for-physical-activity:2`: Table 10.1. Recommended Physical Activity: Duration for good health | Activity | Duration (min.) | | Sleep | 480 | | Occupation (work) | 480 | | Household chores (cleaning, cooking or washing utensils) | 220 | | Personal care / eating / watching TV | 180 | | Leisure time physical activity (different yoga postures, walking, gardening, dancing etc.) | 60 | | Aerobic exercise (brisk walking, running,…
- Adults (age >19–60 years) are recommended to do a minimum of 30–60 minutes of moderate‑intensity aerobic physical activity per day for at least five days a week, or 15 minutes of vigorous‑intensity aerobic activity per day for at least five days a week, or an equivalent combination, plus muscle‑strengthening exercises on at least two days a week.
    - `icmr-nin-dgi-2024:guidelines-for-physical-activity:1`: - If one follows sedentary life style, it is wise to consult a doctor before starting an exercise program. - Exercise intensity and duration should be increased gradually over a period of time. Shortness of breath, pain, nausea, vomiting, and headache are warning signs that your body needs rest. Children and adolescents (>5–19 years): It is recommended to do a minimum of 60 minutes per day of mode…
- Children and adolescents (age >5–19 years) are recommended to do a minimum of 60 minutes per day of moderate‑to‑vigorous intensity activity, including vigorous intensity activities and strength training on at least three days per week.
    - `icmr-nin-dgi-2024:guidelines-for-physical-activity:1`: - If one follows sedentary life style, it is wise to consult a doctor before starting an exercise program. - Exercise intensity and duration should be increased gradually over a period of time. Shortness of breath, pain, nausea, vomiting, and headache are warning signs that your body needs rest. Children and adolescents (>5–19 years): It is recommended to do a minimum of 60 minutes per day of mode…
- Elderly (age >60 years) should follow the adult recommendations and include additional activities that enhance strength and functional balance for three days or more per week.
    - `icmr-nin-dgi-2024:guidelines-for-physical-activity:1`: - If one follows sedentary life style, it is wise to consult a doctor before starting an exercise program. - Exercise intensity and duration should be increased gradually over a period of time. Shortness of breath, pain, nausea, vomiting, and headache are warning signs that your body needs rest. Children and adolescents (>5–19 years): It is recommended to do a minimum of 60 minutes per day of mode…
- A minimum of 30–45 minutes of brisk walking or moderate‑intensity physical activity among adults helps maintain good health.
    - `icmr-nin-dgi-2024:general-tips-for-physical-activity:2`: POINTS TO REGISTER · A minimum 30–45 minutes brisk walk / physical activity of moderate intensity among adults helps in maintaining good health. · Regular physical activity of 60 minutes per day among children can prevent overweight / obesity. · Physical activity controls body weight, reduces fat mass, increases muscle mass and improves immune function. · Physical activity builds strong muscles, b…

### rc-03 (recommendation): What does DGI 2024 say about drinking water?

**Status:** answered

**Expected (golden notes):** Guideline 14 "Drink adequate quantity of water": a healthy person needs about eight glasses (about two litres) of water including beverages a day; boil water when its safety is in doubt; avoid synthetic soft drinks (p. 106–109).

**icmr-nin-dgi-2024**
- A normal healthy person needs to drink about eight glasses (approximately two litres) of water including beverages per day.
    - `icmr-nin-dgi-2024:guideline-14-drink-adequate-quantity-of-water:2`: Why do we need water? Water accounts for 70% of our body weight. It is a constituent of blood and other vital body fluids. Water plays a key role in the elimination of body wastes and regulation of body temperature. The body loses water through sweat, urine and feces. This loss must be constantly made good with clean and potable water. A normal healthy person needs to drink about eight glasses (ap…
- Water is considered safe if it is free from disease‑causing agents and harmful chemical substances, and if fluoride concentration is 1–1.5 mg per litre.
    - `icmr-nin-dgi-2024:guideline-14-drink-adequate-quantity-of-water:2`: Why do we need water? Water accounts for 70% of our body weight. It is a constituent of blood and other vital body fluids. Water plays a key role in the elimination of body wastes and regulation of body temperature. The body loses water through sweat, urine and feces. This loss must be constantly made good with clean and potable water. A normal healthy person needs to drink about eight glasses (ap…
- Boiling water for 10–15 minutes renders it safe by killing disease‑causing organisms and removing temporary hardness.
    - `icmr-nin-dgi-2024:how-is-water-rendered-safe:1`: The simplest and efficient method of rendering water safe is straining and keeping the water boiling for 10–15 minutes. The boiling process kills all disease-causing organisms and also removes temporary hardness. However, boiling will not remove chemical impurities. Tablets each containing 0.5g of chlorine can be used to disinfect 20 litres of water. There are many modern gadgets which could help …
- Chlorine tablets containing 0.5 g of chlorine can disinfect 20 litres of water.
    - `icmr-nin-dgi-2024:how-is-water-rendered-safe:1`: The simplest and efficient method of rendering water safe is straining and keeping the water boiling for 10–15 minutes. The boiling process kills all disease-causing organisms and also removes temporary hardness. However, boiling will not remove chemical impurities. Tablets each containing 0.5g of chlorine can be used to disinfect 20 litres of water. There are many modern gadgets which could help …
- The guideline advises drinking adequate quantities of safe water to meet daily fluid requirements.
    - `icmr-nin-dgi-2024:avoid-alcoholic-beverages:2`: POINTS TO REGISTER · Drink adequate quantities of safe water to meet the daily fluid requirements. · Boil water, when safety of the water is in doubt. · Consume fresh fruits rather than in juice form. · Prefer butter milk, tender coconut water, lemon water etc., as beverages in hot weather. Avoid synthetic soft drinks and carbonated beverages. · Synthetic soft drinks are not substitutes for water …
- When water safety is in doubt, it should be boiled.
    - `icmr-nin-dgi-2024:avoid-alcoholic-beverages:2`: POINTS TO REGISTER · Drink adequate quantities of safe water to meet the daily fluid requirements. · Boil water, when safety of the water is in doubt. · Consume fresh fruits rather than in juice form. · Prefer butter milk, tender coconut water, lemon water etc., as beverages in hot weather. Avoid synthetic soft drinks and carbonated beverages. · Synthetic soft drinks are not substitutes for water …

### rc-04 (recommendation): What extra dietary care does the ICMR guidance recommend during pregnancy and breastfeeding?

**Status:** answered

**Expected (golden notes):** Guideline 2 "Ensure provision of extra food and healthcare during pregnancy and lactation": extra food is needed; include pulses, nuts, fish, milk and eggs; avoid HFSS foods, alcohol and tobacco; drink over 2 litres of fluids a day; take iron-folic acid and calcium supplements as advised (p. 30–37).

**icmr-nin-dgi-2024**
- Consume over 2 litres of fluids per day, including water and other beverages.
    - `icmr-nin-dgi-2024:why-nutritional-care-during-lactation-is-importa:3`: What additional care is required during pregnancy and lactation? Dietary care: It is advised to consume plenty of fluids (over 2 litres per day). This amount of fluid includes water and other beverages. Excess intake of beverages containing caffeine like coffee and tea adversely affect fetal growth and hence should be minimized. The expectant mother should choose foods rich in fibre (around 25g/10…
- Choose foods rich in fibre (around 25 g per 1000 kcal) such as whole‑grain cereals, pulses and vegetables to prevent constipation.
    - `icmr-nin-dgi-2024:why-nutritional-care-during-lactation-is-importa:3`: What additional care is required during pregnancy and lactation? Dietary care: It is advised to consume plenty of fluids (over 2 litres per day). This amount of fluid includes water and other beverages. Excess intake of beverages containing caffeine like coffee and tea adversely affect fetal growth and hence should be minimized. The expectant mother should choose foods rich in fibre (around 25g/10…
- Include a variety of pulses, nuts, fish, milk and eggs daily to ensure adequate protein, minerals, vitamins, essential fatty acids and essential amino acids.
    - `icmr-nin-dgi-2024:why-nutritional-care-during-lactation-is-importa:4`: POINTS TO REGISTER • Follow healthy dietary habit and active lifestyle before conceiving, during pregnancy and lactation (Guideline 1). • For health and well-being of a pregnant woman and her offspring, ensure the woman has appropriate BMI and normal hemoglobin levels. • A woman must be at least 21 years of age at the time of her first pregnancy. • Include a variety of pulses, nuts, fish as well a…
- Avoid high‑sugar, high‑fat and high‑salt (HFSS) foods.
    - `icmr-nin-dgi-2024:why-nutritional-care-during-lactation-is-importa:4`: POINTS TO REGISTER • Follow healthy dietary habit and active lifestyle before conceiving, during pregnancy and lactation (Guideline 1). • For health and well-being of a pregnant woman and her offspring, ensure the woman has appropriate BMI and normal hemoglobin levels. • A woman must be at least 21 years of age at the time of her first pregnancy. • Include a variety of pulses, nuts, fish as well a…
- Take iron‑folic acid (IFA) tablets after 12 weeks of pregnancy and continue them during lactation; a daily folic acid supplement of 500 µg (0.5 mg) is advised during the first trimester.
    - `icmr-nin-dgi-2024:why-nutritional-care-during-lactation-is-importa:4`: POINTS TO REGISTER • Follow healthy dietary habit and active lifestyle before conceiving, during pregnancy and lactation (Guideline 1). • For health and well-being of a pregnant woman and her offspring, ensure the woman has appropriate BMI and normal hemoglobin levels. • A woman must be at least 21 years of age at the time of her first pregnancy. • Include a variety of pulses, nuts, fish as well a…
- During the first six months of lactation add about 600 kcal of energy and 13.6 g of protein to the daily diet; during the next six months add about 520 kcal and 10.6 g of protein, and continue daily iron and folic acid supplements.
    - `icmr-nin-dgi-2024:why-nutritional-care-during-lactation-is-importa:1`: There is an additional demand for calories, proteins and micronutrients during the lactation period, in order to maintain the health of the mother and for optimum breast milk production. During the first six months of lactation, an additional 600 calories of energy and 13.6g of proteins are required in the daily diet. In the next six months, additional requirements are 520 calories of energy and 1…

### df-01 (doc_filtered): What should a balanced plate look like?

**Status:** answered

**Expected (golden notes):** "My Plate for the Day": nutrients from at least eight food groups, with vegetables, fruits, green leafy vegetables, roots and tubers making up about half the plate (p. 16, 23).

**icmr-nin-dgi-2024**
- The plate illustrates proportion of foods from different food groups for a 2000 Kcal Indian diet.
    - `icmr-nin-dgi-2024:what-are-food-groups:3`: The ' My Plate for the Day' (Figure 1.3) developed by the ICMR-National Institute of Nutrition provides a simple guidance to achieve a balanced diet sourcing energy from different food groups. Tables 1.2a & 1.2b show the percent calories from different food groups that would ensure appropriate balance of all nutrients. The plate typically illustrates proportion of foods from different food groups …
- Vegetables, fruits, green leafy vegetables, tubers and roots form essentially half the plate of recommended foods per day.
    - `icmr-nin-dgi-2024:what-are-food-groups:3`: The ' My Plate for the Day' (Figure 1.3) developed by the ICMR-National Institute of Nutrition provides a simple guidance to achieve a balanced diet sourcing energy from different food groups. Tables 1.2a & 1.2b show the percent calories from different food groups that would ensure appropriate balance of all nutrients. The plate typically illustrates proportion of foods from different food groups …
- At least half of the recommended cereals should be whole grains such as millets.
    - `icmr-nin-dgi-2024:what-are-food-groups:3`: The ' My Plate for the Day' (Figure 1.3) developed by the ICMR-National Institute of Nutrition provides a simple guidance to achieve a balanced diet sourcing energy from different food groups. Tables 1.2a & 1.2b show the percent calories from different food groups that would ensure appropriate balance of all nutrients. The plate typically illustrates proportion of foods from different food groups …
- Millets can be consumed to the extent of 30%–40% of total recommended cereals in raw weight.
    - `icmr-nin-dgi-2024:what-are-food-groups:3`: The ' My Plate for the Day' (Figure 1.3) developed by the ICMR-National Institute of Nutrition provides a simple guidance to achieve a balanced diet sourcing energy from different food groups. Tables 1.2a & 1.2b show the percent calories from different food groups that would ensure appropriate balance of all nutrients. The plate typically illustrates proportion of foods from different food groups …
- The plate recommends sourcing macronutrients and micronutrients from a minimum of 10 food groups.
    - `icmr-nin-dgi-2024:what-are-food-groups:3`: The ' My Plate for the Day' (Figure 1.3) developed by the ICMR-National Institute of Nutrition provides a simple guidance to achieve a balanced diet sourcing energy from different food groups. Tables 1.2a & 1.2b show the percent calories from different food groups that would ensure appropriate balance of all nutrients. The plate typically illustrates proportion of foods from different food groups …
- The energy cut‑off level is 250 Kcal for every 100 g of cooked food.
    - `icmr-nin-dgi-2024:what-are-food-groups:3`: The ' My Plate for the Day' (Figure 1.3) developed by the ICMR-National Institute of Nutrition provides a simple guidance to achieve a balanced diet sourcing energy from different food groups. Tables 1.2a & 1.2b show the percent calories from different food groups that would ensure appropriate balance of all nutrients. The plate typically illustrates proportion of foods from different food groups …

### df-02 (doc_filtered): What does the guidance say about trans fats?

**Status:** answered

**Expected (golden notes):** No more than 1% of total energy should come from trans fat of any type; industrially produced trans fats are not part of a healthy diet and should be avoided.

**who-healthy-diet**
- No more than 1% of total energy intake should come from trans fat of any type.
    - `who-healthy-diet:fats:2`: - For adults, limiting the amount of total fat in the diet to 30% or less of total daily energy intake may help to prevent unhealthy weight gain in the adult population. Children have unique energy requirements for optimal growth and development throughout childhood and adolescence and therefore higher total fat intakes may also be acceptable. - The quality of dietary fat is important. Unsaturated…
- Industrially-produced trans fats are not part of a healthy diet and should be avoided.
    - `who-healthy-diet:fats:2`: - For adults, limiting the amount of total fat in the diet to 30% or less of total daily energy intake may help to prevent unhealthy weight gain in the adult population. Children have unique energy requirements for optimal growth and development throughout childhood and adolescence and therefore higher total fat intakes may also be acceptable. - The quality of dietary fat is important. Unsaturated…
- Trans fat includes industrially-produced trans fat found in baked and fried foods and pre‑packaged snacks, and ruminant trans fat found in meat and dairy from ruminant animals.
    - `who-healthy-diet:fats:2`: - For adults, limiting the amount of total fat in the diet to 30% or less of total daily energy intake may help to prevent unhealthy weight gain in the adult population. Children have unique energy requirements for optimal growth and development throughout childhood and adolescence and therefore higher total fat intakes may also be acceptable. - The quality of dietary fat is important. Unsaturated…
- Reducing trans fat intake can be achieved by limiting consumption of baked and fried foods and pre‑packaged snacks that contain industrially‑produced trans fat.
    - `who-healthy-diet:fats:3`: - Fat intake, especially saturated and trans fat, can be reduced by: steaming or boiling instead of frying when cooking; replacing butter, lard and ghee with oils rich in polyunsaturated fat, such as soybean, canola (rapeseed), corn, safflower and sunflower oils; eating reduced-fat dairy foods and lean meats, or trimming visible fat from meat; and limiting the consumption of baked and fried foods,…
- Replacing butter, lard and ghee with oils rich in polyunsaturated fat can help reduce intake of saturated and trans fat.
    - `who-healthy-diet:fats:3`: - Fat intake, especially saturated and trans fat, can be reduced by: steaming or boiling instead of frying when cooking; replacing butter, lard and ghee with oils rich in polyunsaturated fat, such as soybean, canola (rapeseed), corn, safflower and sunflower oils; eating reduced-fat dairy foods and lean meats, or trimming visible fat from meat; and limiting the consumption of baked and fried foods,…

### df-03 (doc_filtered): How quickly should raw milk be chilled after milking, and to what temperature?

**Status:** answered

**Expected (golden notes):** Raw milk should reach the chilling centre or plant within 4 hours of milking and be cooled as soon as practicable to 5 °C or below (p. 28, 88); refrigerated dairy products are transported at 4 °C or less (p. 30).

**fssai-fsms-milk**
- Raw milk should be brought to the collection centre within 4 hours and immediately chilled to a temperature of 4 °C.
    - `fssai-fsms-milk:e-inspection-checklist:1`: MILK & MILK PRODUCT PROCESSING Milk is brought to the collection centre within 4 hours and immediately chilled to a temperature of 4°C or 2…
- Raw milk shall be cooled as soon as practicable to a temperature of 5 °C or below, and must be transported within 4 hours of milking.
    - `fssai-fsms-milk:e-inspection-checklist:5`: i. At village level collection (VLC) a. Proper location, building layout so as to prevent cross contamination from chemicals, insect/pest, biological and other hazardous substances. b. Use of proper milk collection equipment – preferably from SS. c. Ensure use of clean milk storage cans/containers. d. Proper personal hygiene and cleaning /sanitation protocol at the centre. e. Adequate weighing and…

### df-04 (doc_filtered): What hygiene controls are required in poultry slaughter and processing areas?

**Status:** answered

**Expected (golden notes):** Separation between clean and dirty sections with one-way flow (no crossing between live birds, meat and waste); air flows from clean to dirty areas; potable water for washing carcasses; dressed birds chilled below 4 °C within 4 hours of slaughter (p. 26, 32, 37).

**fssai-fsms-poultry**
- Facility walls, partitions, and floors in holding, slaughter, and portioning & retail areas must be made of impervious materials for easy cleaning and to avoid accumulation of dust, blood, meat particles, and microbial growth.
    - `fssai-fsms-poultry:sanitary-hygienic-requirements-for-small-slaught:2`: To ensure hygiene and safety of meat being sold, the following requirements should be followed: 1.3.1. Facility shall be constructed to enable hygienic processing and sale of meat to ensure food safety. 1.3.2. A sign board indicating the type of meat sold shall be displayed prominently. In case more than one type of meat is being sold, care should be taken to avoid cross-contamination. 1.3.3. The …
- The facility must be designed with three separate sections—Holding Area, Slaughter Area, and Portioning & Retail Area—and ensure edible meat does not contact floors, walls, or other fixed structures except those hygienically designed for meat contact.
    - `fssai-fsms-poultry:sanitary-hygienic-requirements-for-small-slaught:1`: To ensure hygiene and safety of meat being sold, the following requirements should be followed: 1.1. Location 1.1.1. The facility shall be located in the areas not subjected to regular and frequent flooding, and shall be free from undesirable odour, smoke, dust or other contaminants. 1.1.2. The facility shall have adequate drainage and provision for cleaning. The facility premise shall be construc…
- All equipment, fittings, and implements such as knives must be made of cleanable, durable, corrosion‑resistant material capable of withstanding repeated cleaning and disinfection.
    - `fssai-fsms-poultry:sanitary-hygienic-requirements-for-small-slaught:2`: To ensure hygiene and safety of meat being sold, the following requirements should be followed: 1.3.1. Facility shall be constructed to enable hygienic processing and sale of meat to ensure food safety. 1.3.2. A sign board indicating the type of meat sold shall be displayed prominently. In case more than one type of meat is being sold, care should be taken to avoid cross-contamination. 1.3.3. The …
- Personnel must follow a personal hygiene programme that prohibits smoking, chewing, eating, spitting, or any unhygienic behavior in processing areas, keep fingernails trimmed, and wash hands frequently with suitable cleanser and potable water.
    - `fssai-fsms-poultry:3-personal-behavior:1`: 1. The slaughter house/processing unit shall implement an effective personal hygiene programme that identifies hygienic behaviour and habits to be followed by personnel to prevent contamination of food. 2. Any behaviour or unhygienic practices which could result in contamination of meat shall be prohibited in meat processing, distribution, storage and handling areas. This includes smoking, chewing…
    - `fssai-fsms-poultry:sanitary-hygienic-requirements-for-small-slaught:4`: To ensure hygiene and safety of meat being sold, the following requirements should be followed: 1.7.1. Facility shall ensure there are no pest infestation which may cause food safety threat. 1.7.2. Facility shall use approved pesticides with appropriate precautions to prevent contamination of meat. Before pesticides are applied all meat should be removed from the room and all equipment and utensil…
- Pest infestation must be prevented by excluding flies, rats, mice, and other vermin; using bait stations, glue traps, approved pesticides; and maintaining a documented pest‑control programme.
    - `fssai-fsms-poultry:3-pest-control:1`: 1. Every suitable measure shall be taken to exclude flies, rats, mice, vermin etc. from the slaughter houses/meat processing unit. 2. Bait stations should be installed outside and Glue traps inside the processing and slaughtering halls. 3. Only approved baits and pesticides should be used. 4. A valid and legal contract with the third party/ pest control service providers should be available in the…
- A quality control programme must include periodic microbiological examination of air, water, hand swabs, and food‑contact surfaces, with records maintained and testing at least once every six months.
    - `fssai-fsms-poultry:10-quality-control:1`: - The Poultry slaughterhouses and processing units shall have a quality control programme in place to include inspection and testing of incoming, in-process and finished products. - Adequate infrastructure including an in-house laboratory facility and / or engaging with an external laboratory facility, withqualified, trained and competent testing personnelshall be available for carrying out testin…

### df-05 (doc_filtered): How long can cooked leftovers be kept in the freezer?

**Status:** answered

**Expected (golden notes):** Cooked meat or poultry 2 to 6 months; chicken nuggets or patties 1 to 3 months; pizza 1 to 2 months. Freezer times are for quality only; food kept at 0 °F (-18 °C) is safe indefinitely.

**foodsafety-cold-storage**
- Cooked leftovers can be kept in the freezer for 2 to 6 months.
    - `foodsafety-cold-storage:cold-food-storage-chart:5`: Table: Cold Food Storage Chart | Food | Type | Refrigerator [40°F (4°C) or below] | Freezer [0°F (-18°C) or below] | |---|---|---|---| | Soups and stews | Vegetable or meat added | 3 to 4 days | 2 to 3 months | | Leftovers | Cooked meat or poultry | 3 to 4 days | 2 to 6 months | | Leftovers | Chicken nuggets or patties | 3 to 4 days | 1 to 3 months | | Leftovers | Pizza | 3 to 4 days | 1 to 2 mont…

### cd-01 (cross_doc): Which cooking oils should I use, and is it OK to reuse oil after deep frying?

**Status:** answered

**Expected (golden notes):** ICMR-NIN: repeated heating of oils generates harmful compounds and must be avoided; used oil should not be mixed with fresh oil; limit ghee and butter; avoid vanaspati (p. 72–73, 101). WHO: unsaturated fats (sunflower, soybean, canola, olive oils) are preferable to saturated fats (butter, ghee, palm and coconut oil); steam or boil instead of frying. The FSSAI documents do not cover oil reuse. Each source must be a separate section.

**icmr-nin-dgi-2024**
- Vegetable oil once used for frying should be filtered and may be used for curry preparation, but should not be used for frying again.
    - `icmr-nin-dgi-2024:repeated-heating-of-oils:1`: The practice of 'reusing' vegetable oils for cooking, (which have been repeatedly heated during food preparations) is very common, both at homes and in commercial establishments. Repeated heating of vegetable oils/fat, results in oxidation of PUFA, leading to the generation of compounds which are harmful/toxic and may increase the risk of cardiovascular diseases and cancer. At household level, veg…
- Used oil should be consumed within a day or two and should not be stored for a long time.
    - `icmr-nin-dgi-2024:repeated-heating-of-oils:1`: The practice of 'reusing' vegetable oils for cooking, (which have been repeatedly heated during food preparations) is very common, both at homes and in commercial establishments. Repeated heating of vegetable oils/fat, results in oxidation of PUFA, leading to the generation of compounds which are harmful/toxic and may increase the risk of cardiovascular diseases and cancer. At household level, veg…
- Repeated heating of cooking oils generates harmful oxidative (polar) compounds and must be avoided.
    - `icmr-nin-dgi-2024:repeated-heating-of-oils:2`: POINTS TO REGISTER · Include foods rich in alpha-linolenic (ALA)/n-3 PUFA such as nuts & seeds, soyabeans, grains/millets, green leafy vegetables and fenugreek seeds. · Prefer marine fish such as salmon, mackerel, trout and tuna (~200gm/week) which are good sources of preferred LC n-3 fatty acids. · Moderate the use of high n-6 PUFA containing oils. · Limit the use of high saturated-fat containing…
- Repeated use of oils used for frying should be avoided, and already used oils should not be mixed with fresh oils and reused.
    - `icmr-nin-dgi-2024:steaming:1`: into contact with steam. Direct contact between vegetable tissue and water is thus avoided, which significantly minimizes the loss of water-soluble vitamins and phytochemical compounds through leaching. Steaming is the best cooking method to increase the level of both antioxidants and polyphenols (which have antioxidant activity) in vegetables and greens. Further, this process makes many nutrients…

**who-healthy-diet**
- Replace butter, lard and ghee with polyunsaturated oils such as soybean, canola (rapeseed), corn, safflower and sunflower oils.
    - `who-healthy-diet:fats:3`: - Fat intake, especially saturated and trans fat, can be reduced by: steaming or boiling instead of frying when cooking; replacing butter, lard and ghee with oils rich in polyunsaturated fat, such as soybean, canola (rapeseed), corn, safflower and sunflower oils; eating reduced-fat dairy foods and lean meats, or trimming visible fat from meat; and limiting the consumption of baked and fried foods,…

### cd-02 (cross_doc): How long can raw chicken stay in the fridge, and how should it be handled to avoid contamination?

**Status:** partial

**Expected (golden notes):** FoodSafety.gov: fresh chicken, whole or pieces, 1 to 2 days refrigerated (frozen: 1 year whole, 9 months pieces). FSSAI poultry: carcasses chilled below 4 °C within 4 hours; refrigerators at 4 °C; clean and dirty sections separated. Separate sections.

**fssai-fsms-poultry**
- Raw chicken (chilled meat) should be stored at or below 4 °C in the refrigerator.
    - `fssai-fsms-poultry:3-9-post-slaughter-requirements:1`: - The temperature in rooms for deskinning, portioning, bone-out, trimming and packing shall be maintained so that meat temperature can be controlled between 10 °C to 12 °C. - All operations in connection with the preparation or packing of chicken / chicken products shall be carried out under hygienic conditions. Particular attention needs to be given to temperature control. - It is important that …
- The cold chain for chicken should not be interrupted, and it must be handled, stored and transported in a manner that protects it from contamination and deterioration.
    - `fssai-fsms-poultry:3-9-post-slaughter-requirements:1`: - The temperature in rooms for deskinning, portioning, bone-out, trimming and packing shall be maintained so that meat temperature can be controlled between 10 °C to 12 °C. - All operations in connection with the preparation or packing of chicken / chicken products shall be carried out under hygienic conditions. Particular attention needs to be given to temperature control. - It is important that …
- Unpacked fresh, chilled, or frozen meat should not be transported with other food products to avoid cross‑contamination.
    - `fssai-fsms-poultry:8-transportation-of-meat-and-meat-products:1`: - While loading in the refrigerated containers, the temperature in the container has to be brought to -12°C (Precooling) so that there is no thawing of the frozen meat cartons while they are loaded. However, in case of chilled products, precooling temperature shall be at or below 4OC - The containers have to be clean and disinfected before loading. - After loading it is sealed and taken to destina…

**icmr-nin-dgi-2024**
- Perishable foods such as meat should be refrigerated, preferably at a temperature of less than 5 °C, to retard multiplication of microorganisms.
    - `icmr-nin-dgi-2024:why-do-food-borne-illnesses-occur:1`: Food-borne illnesses are common particularly with consumption of foods prone to spoilage/contamination such as milk products like khoa, meat, poultry and even improperly stored cooked foods (like rice). Improper processing, handling and cooking, and keeping cooked food in warm conditions for several hours promote bacterial growth and bacterial toxin production, which when consumed can cause food-b…

**Not covered:** Specific storage duration for raw chicken in the refrigerator is not provided in the passages.

### cd-03 (cross_doc): How much salt is it OK to eat in a day, according to the guidelines?

**Status:** answered

**Expected (golden notes):** Both say about 5 g, but each must be stated separately: ICMR-NIN Guideline 11 says not more than 5 g of salt (about 1 teaspoon, ~2 g sodium) per day (p. 90–91); WHO says less than 5 g of salt (2 g sodium) per day for adults. Must not be merged into one "the guidelines say" claim.

**icmr-nin-dgi-2024**
- Maximum recommended salt intake is 5 g per day.
    - `icmr-nin-dgi-2024:are-other-varieties-of-salt-any-better:2`: POINTS TO REGISTER · Use iodized salt · Restrict the intake of added salt (sodium chloride) to a maximum of 5g per day. · Develop a taste for foods/diets that are low in salt from an early age. · Restrict intake of processed and preserved foods such as snack foods, sauces, ketchup, biscuits, chips, cheese and salted fish. · Eat plenty of vegetables and fruits. These are good sources of potassium, …
    - `icmr-nin-dgi-2024:high-bp-leads-to:1`: intakes. The amount of salt consumed is reflected in urinary sodium levels. Restriction of dietary salt decreases the risk of hypertension. Potassium-rich foods such as fresh vegetables and fruits decrease blood pressure. In fact, it is the ratio of sodium to potassium in the diet which is important. Besides increasing blood pressure, excessive salt may also affect stomach mucosa and increase the …

**who-healthy-diet**
- Salt intake should be limited to less than 5 g per day.
    - `who-healthy-diet:salt-sodium-and-potassium:2`: - In many countries, most salt comes from processed foods (e.g. ready meals; processed meats such as bacon, ham and salami; cheese; and salty snacks) or from foods consumed frequently in large amounts (e.g. bread). Salt is also added to foods during cooking (e.g. bouillon, stock cubes, soy sauce and fish sauce) or at the point of consumption (e.g. table salt). - In adults, salt intake should be li…

### cd-04 (cross_doc): What do the guidelines say about limiting sugar?

**Status:** answered

**Expected (golden notes):** ICMR-NIN: sugar less than 5% of total energy for adults (about 20–25 g a day), no added sugar for children under 2, avoid foods and beverages with added sugars (p. 19, 29). WHO: free sugars below 10% of energy, with further benefit at 5% or less. Separate sections.

**who-healthy-diet**
- Free sugars should be limited to less than 10% of total daily energy intake, equivalent to 50 g (about 12 teaspoons) for a 2000‑calorie diet.
    - `who-healthy-diet:sugars:1`: - The consumption of free sugars should be limited to less than 10% of total daily energy intake, which is equivalent to 50 g (or about 12 level teaspoons) for a person of healthy body weight consuming about 2000 calories per day. Limiting further to 5% or less of total daily energy intake may provide additional health benefits. - Consumption of free sugars should be limited throughout the life co…
- Limiting free sugars to 5% or less of total daily energy intake may provide additional health benefits.
    - `who-healthy-diet:sugars:1`: - The consumption of free sugars should be limited to less than 10% of total daily energy intake, which is equivalent to 50 g (or about 12 level teaspoons) for a person of healthy body weight consuming about 2000 calories per day. Limiting further to 5% or less of total daily energy intake may provide additional health benefits. - Consumption of free sugars should be limited throughout the life co…
- Free sugars should be limited throughout the life course.
    - `who-healthy-diet:sugars:1`: - The consumption of free sugars should be limited to less than 10% of total daily energy intake, which is equivalent to 50 g (or about 12 level teaspoons) for a person of healthy body weight consuming about 2000 calories per day. Limiting further to 5% or less of total daily energy intake may provide additional health benefits. - Consumption of free sugars should be limited throughout the life co…
- Free sugars include monosaccharides and disaccharides added to foods and beverages and sugars naturally present in honey, syrups, fruit juices and fruit juice concentrates.
    - `who-healthy-diet:sugars:1`: - The consumption of free sugars should be limited to less than 10% of total daily energy intake, which is equivalent to 50 g (or about 12 level teaspoons) for a person of healthy body weight consuming about 2000 calories per day. Limiting further to 5% or less of total daily energy intake may provide additional health benefits. - Consumption of free sugars should be limited throughout the life co…
- Reducing free‑sugar consumption should be done without using non‑sugar sweeteners.
    - `who-healthy-diet:sugars:1`: - The consumption of free sugars should be limited to less than 10% of total daily energy intake, which is equivalent to 50 g (or about 12 level teaspoons) for a person of healthy body weight consuming about 2000 calories per day. Limiting further to 5% or less of total daily energy intake may provide additional health benefits. - Consumption of free sugars should be limited throughout the life co…

**icmr-nin-dgi-2024**
- Sugar may be consumed but must be restricted to 25–30 g per day.
    - `icmr-nin-dgi-2024:what-are-food-groups:6`: Note: One may consume sugar, but it must be restricted to 25–30 grams per day. To adjust the total calories, cereals must be reduced if sugar is taken. + Prescribed amount of vegetables (excluding potato) may be consumed either in cooked form or salad # Prefer fresh fruits (avoid juices)…

### cd-05 (cross_doc): How should fresh fruits and vegetables be cleaned to keep them safe to eat?

**Status:** answered

**Expected (golden notes):** ICMR-NIN: wash vegetables and fruits thoroughly before use, but not after cutting or peeling, and do not soak cut vegetables (p. 97, 105). FSSAI: wash with potable water to remove soil and contamination (p. 37). Separate sections.

**fssai-fsms-fruits-vegetables**
- Fruits and vegetables should be cleaned properly to remove physical hazards through manual sorting or use of equipment.
    - `fssai-fsms-fruits-vegetables:2-4-hygiene-control-in-specific-process-steps:1`: Preparatory operations leading to the finished product and the packaging operations should be so timed as to permit expeditious handling of consecutive units in production under conditions which would prevent contamination, deterioration, spoilage, or the development of pathogenic or toxicogenic microorganisms. The processing methods should ensure compliance to the relevant standard. - Sorting & G…
- Cleaning should involve washing as needed to remove soil or other contamination.
    - `fssai-fsms-fruits-vegetables:2-4-hygiene-control-in-specific-process-steps:1`: Preparatory operations leading to the finished product and the packaging operations should be so timed as to permit expeditious handling of consecutive units in production under conditions which would prevent contamination, deterioration, spoilage, or the development of pathogenic or toxicogenic microorganisms. The processing methods should ensure compliance to the relevant standard. - Sorting & G…
- Water used for washing, rinsing, or conveying final food products should be of potable quality.
    - `fssai-fsms-fruits-vegetables:2-4-hygiene-control-in-specific-process-steps:1`: Preparatory operations leading to the finished product and the packaging operations should be so timed as to permit expeditious handling of consecutive units in production under conditions which would prevent contamination, deterioration, spoilage, or the development of pathogenic or toxicogenic microorganisms. The processing methods should ensure compliance to the relevant standard. - Sorting & G…
- Washing may be done with potable water, ozonated water, or chlorinated water.
    - `fssai-fsms-fruits-vegetables:2-4-hygiene-control-in-specific-process-steps:2`: Same equipment should not be used for both treated and untreated products without adequate cleaning and disinfection before use with treated products. - Pre-treatment for minimally processed Fruits & Vegetables: Disinfection is one of the most critical processing steps in fresh-cut fruits and vegetable production. Washing need to be designed to remove dirt, dust and reduce microorganisms, whereas,…
- Disinfection after washing is performed to kill contaminated microorganisms.
    - `fssai-fsms-fruits-vegetables:2-4-hygiene-control-in-specific-process-steps:2`: Same equipment should not be used for both treated and untreated products without adequate cleaning and disinfection before use with treated products. - Pre-treatment for minimally processed Fruits & Vegetables: Disinfection is one of the most critical processing steps in fresh-cut fruits and vegetable production. Washing need to be designed to remove dirt, dust and reduce microorganisms, whereas,…

**icmr-nin-dgi-2024**
- Food stuffs should be washed thoroughly in running water or peeled to minimize pesticide residues.
    - `icmr-nin-dgi-2024:guideline-12-consume-safe-and-clean-foods:2`: How to minimize pesticide residue in foods? Pesticides, used during cultivation of crops, can remain as residues in foodstuffs, especially vegetables and fruits. Exposure of the population to pesticide residues may be harmful and can be minimized by washing the food stuffs thoroughly in running water or by peeling. Cooking and other processes can also reduce such residues. Insect control operation…
- Vegetables and fruits should be washed thoroughly before use.
    - `icmr-nin-dgi-2024:safe-use-of-cookware:2`: POINTS TO REGISTER · Wash hands with soap and water before touching food, utensils or cooking. · Buy food items from reliable sources after careful examination. · Wash vegetables and fruits thoroughly before use. · Wash the surface of eggs thoroughly before preserving and before preparation. · Wash and cook meat thoroughly. · Store raw and cooked foods separately and properly to prevent cross-cont…

### nm-01 (near_miss): What does WHO say about salt and blood pressure?

**Status:** answered

**Expected (golden notes):** High sodium (salt) intake is associated with increased blood pressure, which can lead to cardiovascular disease; potassium can mitigate the effect; adults should keep salt below 5 g a day. Population guidance, not personal medical advice, so it must be answered.

**who-healthy-diet**
- High intake of sodium (salt) is associated with increased blood pressure, which can lead to cardiovascular disease.
    - `who-healthy-diet:salt-sodium-and-potassium:1`: Sodium and potassium are essential minerals but high intake of sodium (salt) is associated with increased blood pressure which can lead to cardiovascular disease. Salt intake is high in many parts of the world and people are often unaware of the amount of salt they consume. Potassium can mitigate the negative effects of elevated sodium consumption on blood pressure.…
- Potassium can mitigate the negative effects of elevated sodium consumption on blood pressure.
    - `who-healthy-diet:salt-sodium-and-potassium:1`: Sodium and potassium are essential minerals but high intake of sodium (salt) is associated with increased blood pressure which can lead to cardiovascular disease. Salt intake is high in many parts of the world and people are often unaware of the amount of salt they consume. Potassium can mitigate the negative effects of elevated sodium consumption on blood pressure.…

### nm-02 (near_miss): What share of daily energy should come from free sugars, according to WHO?

**Status:** answered

**Expected (golden notes):** Less than 10% of total daily energy intake; limiting to 5% or less may give additional benefits. The page also gives "50 g for a person consuming about 2000 calories" as an illustration — this is not a personal calorie target and must not trigger the output guard.

**who-healthy-diet**
- Free sugars should be limited to less than 10% of total daily energy intake.
    - `who-healthy-diet:sugars:1`: - The consumption of free sugars should be limited to less than 10% of total daily energy intake, which is equivalent to 50 g (or about 12 level teaspoons) for a person of healthy body weight consuming about 2000 calories per day. Limiting further to 5% or less of total daily energy intake may provide additional health benefits. - Consumption of free sugars should be limited throughout the life co…
- Limiting free sugars to 5% or less of total daily energy intake may provide additional health benefits.
    - `who-healthy-diet:sugars:1`: - The consumption of free sugars should be limited to less than 10% of total daily energy intake, which is equivalent to 50 g (or about 12 level teaspoons) for a person of healthy body weight consuming about 2000 calories per day. Limiting further to 5% or less of total daily energy intake may provide additional health benefits. - Consumption of free sugars should be limited throughout the life co…

### nm-03 (near_miss): What do the Indian dietary guidelines say about diet and preventing diabetes?

**Status:** answered

**Expected (golden notes):** Healthy diets and physical activity can reduce coronary heart disease and hypertension and prevent up to 80% of type 2 diabetes (p. 15); regular consumption of HFSS and ultra-processed foods increases the risk of diabetes and other NCDs (Guideline 15, p. 110).

**icmr-nin-dgi-2024**
- Obesity increases the risk of diabetes.
    - `icmr-nin-dgi-2024:why-should-we-prevent-abdominal-overall-obesity:1`: There are several negative health consequences of obesity. Excessive body weight causes low-grade chronic inflammation and increases the risk of heart disease, hypertension, diabetes, gallstones, fatty liver disease, certain types of cancers, osteoarthritis, psycho-social problems and also impairs immunity. Obesity is often associated with increased levels of low-density lipoproteins ('bad' choles…
- To maintain appropriate weight and waist circumference, one must include fresh vegetables in every meal, consume whole grains, pulses and beans, and must avoid sugar, processed products, fruit juices and high‑fat, sugar, salt (HFSS) foods.
    - `icmr-nin-dgi-2024:why-should-we-prevent-abdominal-overall-obesity:1`: There are several negative health consequences of obesity. Excessive body weight causes low-grade chronic inflammation and increases the risk of heart disease, hypertension, diabetes, gallstones, fatty liver disease, certain types of cancers, osteoarthritis, psycho-social problems and also impairs immunity. Obesity is often associated with increased levels of low-density lipoproteins ('bad' choles…
- Regular physical activity and yoga are crucial to maintain good health and weight.
    - `icmr-nin-dgi-2024:why-should-we-prevent-abdominal-overall-obesity:1`: There are several negative health consequences of obesity. Excessive body weight causes low-grade chronic inflammation and increases the risk of heart disease, hypertension, diabetes, gallstones, fatty liver disease, certain types of cancers, osteoarthritis, psycho-social problems and also impairs immunity. Obesity is often associated with increased levels of low-density lipoproteins ('bad' choles…
- Regular consumption of ultra‑processed foods or high‑fat, sugar, salt (HFSS) foods is known to increase the risk of diabetes.
    - `icmr-nin-dgi-2024:guideline-15-minimize-the-consumption-of-high-fa:1`: RATIONALE Ultra-processed foods (UPFs) are often high in fat, sugar and salt (HFSS). Regular consumption of UPFs or HFSS are known to increase the risk of non-communicable diseases like diabetes, hypertension, cardiovascular diseases, etc.…
- A nutritionally adequate or balanced diet should be consumed through a wise choice of food items from a variety of food groups.
    - `icmr-nin-dgi-2024:guideline-1-eat-a-variety-of-foods-to-ensure-a-b:1`: RATIONALE Nutritionally adequate diet or a balanced diet should be consumed through a wise choice of food items from a variety (diverse) of food groups.…

### nm-04 (near_miss): Does WHO set a limit on total fat intake?

**Status:** answered

**Expected (golden notes):** For adults, total fat at 30% or less of total daily energy; at least 15% of energy from fat; saturated fat no more than 10% and trans fat no more than 1%.

**who-healthy-diet**
- For adults, limiting the amount of total fat in the diet to 30% or less of total daily energy intake.
    - `who-healthy-diet:fats:2`: - For adults, limiting the amount of total fat in the diet to 30% or less of total daily energy intake may help to prevent unhealthy weight gain in the adult population. Children have unique energy requirements for optimal growth and development throughout childhood and adolescence and therefore higher total fat intakes may also be acceptable. - The quality of dietary fat is important. Unsaturated…
- In adults, a minimum of 15% of the energy consumed per day should be from fat, up to 30% of total daily calories.
    - `who-healthy-diet:fats:1`: Fat is an essential nutrient for proper functioning of cells in the body, and two fatty acids – linoleic acid and α-linolenic acid – can only be obtained from the diet. Therefore, in adults, a minimum of 15% of the energy consumed per day should be from fat, up to 30% of total daily calories or more as described below.…

