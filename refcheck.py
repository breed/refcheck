# This script extracts references from a PDF file and checks their validity.
# It was initially generated by copilot but modified quite a bit to actually work.
import os
import unicodedata
from datetime import datetime
from readline import append_history_file

import click
from pymupdf import *

EXTRACTION_FLAGS = TEXT_PRESERVE_LIGATURES | TEXT_PRESERVE_WHITESPACE | TEXT_MEDIABOX_CLIP | TEXT_CID_FOR_UNKNOWN_UNICODE

CURRENT_YEAR = datetime.now().year
from os.path import isdir

import fitz  # PyMuPDF
import re
import requests
import enchant

DOI_ORG_PREFIX = "https://doi.org/"

DOI_ORG_API = "https://doi.org/api/handles/"

OPENALEX_API = "https://api.openalex.org/works"

URL_PATTERN = re.compile(r'https?:(//\S*)?$')

WORDS = enchant.Dict("en_US")

def _strip_prefix(s: str, prefix: str) -> str:
    return s[len(prefix):] if s.startswith(prefix) else s


# This massivly gross hack (which totally works) is brought to
# you by the wizard of https://stackoverflow.com/a/66737414
# it's gross, but it works and i don't see a better way...
def make_combining_form(diacritic):
    if unicodedata.category(diacritic) not in ("Sk", "Lm"):
        return None

    name = unicodedata.name(diacritic)
    name = _strip_prefix(name, "MODIFIER LETTER ")
    name = _strip_prefix(name, "COMBINING ")
    try:
        return unicodedata.lookup("COMBINING " + name)
    except KeyError:
        return None


def fix_accents(text):
    converted = ''
    accent = None
    for c in text:
        if accent:
            converted += unicodedata.normalize("NFC", c + accent)
            accent = None
        else:
            accent = make_combining_form(c)
            if not accent:
                converted += c
    return converted


# remove all accents and non alpha characters from a string
# we did all that work above and now we are going to undo it for comparisons
def just_the_chars(text, space_ok=False):
    alphatext = ''
    for c in unicodedata.normalize("NFD", text):
        if unicodedata.category(c)[0] == 'L' or (space_ok and c.isspace()):
            alphatext += c
    return alphatext


def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""

    for page in doc:
        text_blocks = page.get_text_blocks(flags=EXTRACTION_FLAGS | TEXT_IGNORE_ACTUALTEXT)
        for text_block in text_blocks:
            for line in fix_accents(text_block[4]).split("\n"):
                yield line


def extract_references(text_lines):
    # Roughly extract references section
    for line in text_lines:
        references_section = re.search(r'references|bibliography', line, flags=re.IGNORECASE)
        if references_section:
            break
    ref = None
    for line in text_lines:
        if ref and ref.startswith("[3] Cdc"):
            pass
        if line.startswith("["):
            if ref:
                yield ref
            ref = line
            continue
        if ref:
            # if we have a line break in the middle of a URL we don't want to add a space
            if URL_PATTERN.search(ref):
                ref += line
            else:
                # fix any hyphenated lines
                if ref.endswith("-"):
                    # get the last word from ref and the first word from line
                    first_word_match = re.search(r'(\w+)-$', ref)
                    first_word = first_word_match.group(1) if first_word_match else None
                    last_word_match = re.search(r'\w+', line)
                    last_word = last_word_match.group() if last_word_match else None
                    if first_word and not first_word.isalpha():
                        first_word = None
                    if last_word and not last_word.isalpha():
                        last_word = None
                    if first_word and len(first_word) > 1 and first_word.isupper():
                        # horrible hack. MGTBench can get hyphenated and the following rule will match it incorrectly
                        ref = ref[:-1] + line
                    elif not first_word or not last_word or not WORDS.check(first_word+last_word) or last_word[0].isupper():
                        # if they aren't two parts of a word or the last word is capitalized (probably a name) preserve the hyphen
                        ref = ref + line
                    else:
                        # remove the hyphen
                        ref = ref[:-1] + line
                else:
                    ref += " " + line
    if ref:
        yield ref


#    ref_candidates = re.split(r'\n\d+\.\s+|\n(?=\[?\d+\]?\s+)', references_section)
#   references = [ref.strip() for ref in ref_candidates if len(ref.strip()) > 10]
#  return references


def find_urls_or_dois(ref):
    urls = re.findall(r'https?://\S+', ref)
    dois = re.findall(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+', ref, flags=re.IGNORECASE)
    # The DOI search doesn't seem to work properly
    dois = []
    # Remove trailing periods from URLs
    return [url.rstrip('.').rstrip(',') for url in urls + ["https://doi.org/" + doi for doi in dois]]


def check_url_validity(url):
    try:
        if url.startswith(DOI_ORG_PREFIX):
            url = DOI_ORG_API + url[len(DOI_ORG_PREFIX):]
        response = requests.get(url, allow_redirects=True, timeout=10)
        # we are going to take 403 as meaning that it could be there...
        return response.status_code < 400 or response.status_code == 403
    except requests.RequestException:
        return False


def search_openalex(title):
    try:
        response = requests.get(OPENALEX_API, params={"search": title, "per-page": 1}, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data
    except requests.RequestException:
        return None
    return None


def normalize_quotes(ref: str) -> str:
    # Define a dictionary of different double quote characters to replace
    quote_replacements = {'“': '"', '”': '"', '„': '"', '‟': '"', '«': '"', '»': '"'}

    # Replace each quote character in the dictionary with the standard double quote
    for old_quote, new_quote in quote_replacements.items():
        ref = ref.replace(old_quote, new_quote)
    return ref


def extract_possible_title(ref):
    # get the reference without the authors
    ref = ref[find_end_of_authors(ref):].strip()
    # if there is a (, the authors are using a format that has a date before the title
    if ref.startswith("("):
        end_paren = ref.find(")")
        # there may be a comma or period after the )
        if ref[end_paren+1] != " ":
            end_paren += 1
        ref = ref[end_paren+1:].strip()

    if ref.startswith('"'):
        # we have a quoted title
        end_quote = ref.find('"', 1)
        # we add 2 to end_quote to skip the " and punctuation after it
        return ref[1:end_quote].rstrip(",").rstrip(".").strip(), ref[end_quote + 2:].strip()
    else:
        # we don't have a quoted title, so we look for the first period
        period = ref.find(". ")
        return (ref[:period].strip(), ref[period+1:].strip())


def looks_like_title(ref, period):
    potential_title = ref[period:].strip()
    # Check if the potential title starts with a quote, which is common in some styles
    if potential_title.startswith('"'):
        return True
    words = potential_title.split()
    if not words:
        return False
    # if the first word has a colon, it is probably a title
    if ':' in potential_title[0]:
        return True

    # Titles don't start with and
    if potential_title.startswith("and"):
        return False

    # Names are always capitalized, so a lower case word is probably a title
    if potential_title[0].islower():
        return True

    # Do we have at least 3 words?
    if len(words) < 3:
        return False

    return True


def find_end_of_authors(ref):
    title_start_with_quote = ref.find(' "')
    if title_start_with_quote != -1:
        # we have a quoted title
        return title_start_with_quote

    period = 0
    while True:
        # the author list should end with a period
        period = ref.find(". ", period + 1)
        if period == -1:
            break
        # move period past the ". "
        period += 2
        # a hack to make sure we didn't get stuck on an initial.
        # if the next ". " also precedes a capital letter, we are not at the end of the authors
        next_period = ref.find(". ", period)
        if next_period != -1 and ref[next_period-1].isupper():
            continue
        # this is a super gross hack (there are some ugly bibliographies out there!)
        # we aren't done with the authors if there is an "and" as the next word
        rest = ref[period:]
        if rest.startswith("and ") or rest.startswith("et ") or rest.startswith("& "):
            continue
        return period

    # ugh! it looks like they have commas before the title, let's do our hack!
    comma = ref.find(",")
    comma += 1
    while not looks_like_title(ref, comma):
        comma = ref.find(",", comma) + 1
        if not comma:
            return 0
    return comma

def extract_possible_year(after_title):
    # Heuristic: look for a 4-digit year
    years = re.findall(r'[ (]((19|20)\d{2})([ ),;.]|$)', after_title)
    for y in years:
        year = int(y[0])
        # 100 year old citations are suspect
        if (CURRENT_YEAR - 100) < year < CURRENT_YEAR + 1:
            return year
    return None


def extract_possible_author_last_names(ref):
    end_of_authors = find_end_of_authors(ref)
    # We assume the first part is the author list
    author_list = ref[0:end_of_authors].strip().rstrip(",").rstrip(".")
    # Remove the [*] at the beginning
    author_list = re.sub(r'^\[\d+\]\s*', '', author_list)
    # We are assuming the biggest part of the name is the last name
    raw_author_split = re.split(", | and ", author_list)
    author_last_names = []
    for author in  raw_author_split:
        author = author.strip()
        if not author:
            continue
        # looks like we hit a date
        if re.search(r'\d', author):
            break
        # Remove any initials or periods from the name
        name_parts = [n for n in author.split(' ') if len(n) > 1 and '.' not in n and n[0].isupper() and not n.isupper()]
        if name_parts:
            last_name = name_parts[-1]
            if last_name in ["et", "al", "al.", "et.", "others"]:
                # skip the etc words
                continue
            if re.compile(r'[^a-z-]', re.IGNORECASE).search(last_name):
                # skip any names with non-ASCII characters (the PDF reader messes them up!)
                continue
            # accents vary in bibliographies and the original paper, so strip them for
            # comparison purposes
            author_last_names.append(just_the_chars(last_name))
    return author_last_names


def find_missing_authors(authors, item_authors):
    missing = []
    for author in authors:
        found = False
        for iauthor in item_authors:
            if author.lower() in iauthor.lower():
                found = True
                break
        if not found:
            missing.append(author)
    return missing


def check_references_validity(references):
    results = []
    sketchy = []
    for ref in references:
        links = find_urls_or_dois(ref)
        result = ""
        sketchy_problem = []

        if links:
            valid = all(check_url_validity(url) for url in links)
            if not valid:
                sketchy_problem.append("Invalid DOI or URL: " + ", ".join(links))
            result += str(links) + ("Valid (link)" if valid else "Invalid (link)") + "\n"
        if not links or all("doi" in link for link in links):
            (title, after_title) = extract_possible_title(ref)
            year = extract_possible_year(after_title)
            authors = extract_possible_author_last_names(ref)
            result += "Checking Alex for: " + title + "\n"
            alex_ref = search_openalex(title)
            found_title = False
            found_year = False
            missing_authors = []
            if alex_ref and alex_ref['meta']['count'] > 0:
                found_titles = []
                for item in alex_ref['results']:
                    result += f"Alex: "
                    # accents and other characters that might vary
                    item_authors = [just_the_chars(x['author']['display_name'], space_ok=True) for x in item['authorships']]

                    result += ", ".join(item_authors) + ', '
                    item_title = item['title'].replace("\n", " ")
                    item_date = item["publication_date"]
                    result += item_title + ", " + item_date + ", "
                    if "locations" not in item:
                        result += "No locations\n"
                    else:
                        for location in item["locations"]:
                            if "is_published" not in location or not location["is_published"]:
                                result += "not published" + ";"
                            if "source" in location and location["source"]:
                                result += location["source"]["display_name"] + ";"
                            else:
                                result += "No source" + ";"
                    if title and just_the_chars(title.lower()) == just_the_chars(item_title.lower()):
                        found_title = True
                        missing_authors = find_missing_authors(authors, item_authors)
                        found_year = year and str(year) in item_date
                    else:
                        t1 = just_the_chars(title.lower())
                        t2 = just_the_chars(item_title.lower())
                        pass

                if not found_title:
                    sketchy_problem.append(f"Could not find title {title} in published sources: {";".join(found_titles)}.")
                else:
                    if year and not found_year:
                        sketchy_problem.append(f"Could not find year {year} in published sources.")
                    if missing_authors:
                        sketchy_problem.append(f"Could not find authors {",".join(missing_authors)} in published sources.")

            else:
                result += "No OpenAlex match"
                if not links:
                    sketchy_problem.append("No OpenAlex match")

        if sketchy_problem:
            sketchy.append((ref, result, sketchy_problem))

        results.append((ref, result))
    return results, sketchy


@click.command()
@click.argument('pdf_path', type=click.Path(exists=True))
@click.option('--show_all_results', is_flag=True, default=False, help='Show all results, not just sketchy ones')
@click.option('--dump-info', is_flag=True, default=False, help='Just dumpe the info gleaned from the PDF')
def main(pdf_path, show_all_results, dump_info):
    print(f"{pdf_path} exists {os.path.exists(pdf_path)} and is a directory {isdir(pdf_path)}")
    if isdir(pdf_path):
        pdfs = []
        for root, dirs, files in os.walk(pdf_path):
            for file in [os.path.join(root, f) for f in files if f.endswith('.pdf')]:
                pdfs.append(file)
        # sort them so that numerical order is preserved (assuming the numbers are less than 1,000,000
        for file in sorted(pdfs, key=lambda x: os.path.sep.join([p.zfill(6) if p.isdigit() else p for p in x.split(os.path.sep)])):
            check_references(file, show_all_results, dump_info)
            print("-----------------------------\n")
    else:
        check_references(pdf_path, show_all_results, dump_info)


def extract_info(references):
    for ref in references:
        links = find_urls_or_dois(ref)
        authors = extract_possible_author_last_names(ref)
        (title, after_title) = extract_possible_title(ref)
        year = extract_possible_year(after_title)
        print(f"('{ref}'\n{year}, {authors}, '{title}')\n")


def sanitize_ref(ref):
    ref = normalize_quotes(ref)
    while "  " in ref:
        ref = ref.replace("  ", " ")
    return ref

def check_references(pdf_path, show_all_results, dump_info):
    print(f"Extracting references from: {pdf_path}")
    text_lines = extract_text_from_pdf(pdf_path)
    references = [sanitize_ref(x) for x in extract_references(text_lines)]
    print(f"Found {len(references)} references.\n")
    if dump_info:
        extract_info(references)
    else:
        (results, sketchy) = check_references_validity(references)

        if show_all_results:
            for (ref, status) in results:
                print("Search result: " + status)

        if sketchy:
            print("*** Sketchy references:")
            for (ref, result, sketchy_problem) in sketchy:
                print("***************")
                print("Sketchy Reference: " + ref)
                print("Sketchy problem: " + "; ".join(sketchy_problem))
                print("Sketchy result: " + result)
            print()

if __name__ == "__main__":
    main()
