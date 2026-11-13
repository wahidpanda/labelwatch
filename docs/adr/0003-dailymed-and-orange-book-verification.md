# 0003: DailyMed and Orange Book details verified against real responses

Date: 2026-11-13. Status: accepted. Covers every Phase 2 "(verify)" item in section 7.

## DailyMed REST v2

- `spls.json` returns `{"metadata": {...}, "data": [...]}`. Each item has `setid`, `title`,
  `spl_version` (int) and `published_date` as `"Oct 30, 2026"`. Pagination uses `page` and
  `pagesize`; `metadata.total_pages` and `metadata.next_page_url`. Missing values are the
  string `"null"`, not JSON null.
- `spls.json?application_number=NDA009218` works and returns every set filed under that
  application, including repackager copies. We use it as the primary set lookup (see below).
- `spls/{setid}/history.json` returns `data` as one object, not a list:
  `{"spl": {"setid", "title"}, "history": [{"spl_version", "published_date"}]}`. The history
  does not always start at version 1 (a set at version 25 listed only versions 20 to 25), so
  "all versions" means all versions DailyMed still lists.
- `getFile.cfm?type=zip&setid=..&version=N` returns `application/zip` containing one SPL XML
  file plus images (images dominate the size, about 0.5 MB per version). We stream the ZIP to a
  spooled temp file, read only the `.xml` member, hash the ZIP, and discard it.
- The labeler is not a separate field in `spls.json`; it is the trailing `[...]` in `title`.

## SPL XML

- Application numbers live at `manufacturedProduct/.../subjectOf/approval/id/@extension`
  with `@root="2.16.840.1.113883.3.150"`, e.g. `NDA021409`, `ANDA203438`. One SPL can list
  several (one per product); we take the set of distinct values.
- Version and label date: `/document/versionNumber/@value` and `/document/effectiveTime/@value`
  (`YYYYMMDD`). Per section 3, lag uses the DailyMed `published_date` from the history API.
- All LOINC codes in section 7 step 5 were found on real labels. The pregnancy section
  (42228-7) is nested inside use in specific populations (43684-0). When extracting a section
  we skip nested sections that are themselves extracted, so text is not stored twice.
- Old-format labels (2010 Singulair repackager copy) use 42232-9 precautions and 34084-4
  adverse reactions with no 43685-7, confirming both structures must be parsed.

## Orange Book products.txt

- Header (tilde-delimited):
  `Ingredient~DF;Route~Trade_Name~Applicant~Strength~Appl_Type~Appl_No~Product_No~TE_Code~Approval_Date~RLD~RS~Type~Applicant_Full_Name`.
- `Appl_Type` is `N` (NDA) or `A` (ANDA), not the long form. `Appl_No` is zero padded to six
  digits; DailyMed uses `NDA` or `ANDA` plus the same six digits.
- `DF;Route` is one field, e.g. `TABLET, CHEWABLE;ORAL`.
- `Strength` can carry annotations such as
  `1MG **Federal Register determination that product was not discontinued...**`; we strip the
  `**...**` part before matching.
- `RLD` stays `Yes` on a discontinued brand (Coumadin, NDA 009218). `RS` (reference standard)
  can sit on an ANDA. Linking uses `RLD`.

## Set discovery and roles

Instead of searching by drug name and then parsing the approval element of every set, we take
each application for the ingredient from the Orange Book and ask DailyMed for its sets by
application number. Role follows from the application: NDA with RLD = brand, NDA without RLD =
authorized_generic, ANDA = generic. The approval element is still parsed from every downloaded
version and stored as evidence.

Repackager heuristic: a set is a likely repackager when the labeler in its title shares no
significant word with the Orange Book applicant name. Repackager sets are stored with all
version metadata, but their section text is not downloaded by default (they copy their source
and would inflate counts and bandwidth).

## Seed drug caveat: warfarin

The Bristol Myers Squibb Coumadin label is no longer on DailyMed. Only two repackager copies
remain (last published 2012 and 2013). Warfarin brand events after 2013 therefore cannot be
detected. Warfarin stays in the seed list because Phase 2 acceptance uses it, but it should be
replaced by a seed whose brand label is still active before reporting headline numbers.
