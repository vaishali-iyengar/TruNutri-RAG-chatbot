# Problem Statement

## Dietary Guidance RAG Chatbot

### Brief

Build the prototype of a chatbot that answers questions about food, nutrition and food safety. Put a retrieval layer under the chatbot, so it answers only from official public dietary guidance documents. Every claim carries a citation. When the guidance doesn't cover a question, the assistant says so.

In the final project this becomes the service that answers "is this a reasonable way to eat" and "how long can I keep this in the fridge".

Meanwhile the real guidance exists. Health authorities publish long, careful, boring PDFs on exactly this. No API, just written prose, and almost nobody reads them. That gap is what RAG is for.

Nutrient numbers for individual foods are different data and don't belong here. Those come from a structured database in Milestone 3.

### What you build

1. **Corpus.** Gather 5 to 7 public guidance documents from recognised authorities. National nutrition institutes, food safety regulators and international health bodies all work. Written prose only, so anything with a clean API behind it doesn't belong here. Store publisher, year, source URL and retrieval date with every document.

2. **Chunking.** Every chunk carries the document name, publisher, year and section heading. These documents are full of tables and numbered recommendations that fixed-size chunking will cut in half. Say in the README what you chose and what it cost you.

3. **Retrieval.** A vector index over the chunks, supporting retrieval across all documents and retrieval filtered to one named document.

4. **Answer layer.** The assistant answers only from retrieved chunks. Every claim carries a citation showing document name, publisher, year and a link.

5. **Cross-document questions.** Some questions have two documents with something to say, like cooking oil, where a nutrition institute and a food safety regulator both weigh in. Answer per document, with separate citations. Never blend two sources into one claim about what "the guidelines say".

6. **Two kinds of refusal.** You need both.
   - **Not in the corpus:** When the retrieved chunks don't hold the answer, the assistant says the guidance doesn't cover it and names what it searched.
   - **Out of scope by design:** No medical advice, no calorie or weight targets, nothing about what anyone should weigh. It declines and points the person to a qualified professional. Enforce this in code.

### Public guidance documents / URLs to be used

- EFSA — Food Composition — https://www.efsa.europa.eu/en/microstrategy/food-composition-data-2026
- WHO/FAO JECFA Reports & Evaluations — https://www.who.int/groups/joint-fao-who-expert-committee-on-food-additives-%28jecfa%29/publications/reports
- Health Canada — Canadian Nutrient File — https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data/nutrient-value-some-common-foods-2008.html
- ICMR-NIN — Dietary Guidelines for Indians 2024 — https://nin.res.in/dietaryguidelines/pdfjs/locale/DGI_2024.pdf
- FSSAI — Food Safety Management System (FSMS) Guidance Documents:
  - Milk — https://www.fssai.gov.in/docs/business/guidance/Guidance_Document_Milk_14_03_2019.pdf
  - Fruits & Vegetables — https://www.fssai.gov.in/docs/business/guidance/FSMS_Guidance_Document_FruitsVegetable_15_03_2019.pdf
  - Spices — https://www.fssai.gov.in/docs/business/guidance/Guidance_Document_Spices_23_10_2018.pdf
  - Poultry — https://www.fssai.gov.in/docs/business/guidance/Guidance_Document_Poultry_06_01_2020.pdf
  - Fish — https://www.fssai.gov.in/docs/business/guidance/Guidance_Document_Fish_01_06_2018.pdf
- FSSAI — Food Products Standards — https://fssai.gov.in/standards/product-standards
- WHO — Healthy Diet — https://www.who.int/news-room/fact-sheets/detail/healthy-diet
- FoodSafety.gov — Cold Food Storage Charts — https://www.foodsafety.gov/food-safety-charts/cold-food-storage-charts
