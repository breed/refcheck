# This script extracts references from a PDF file and checks their validity.
# It was initially generated by copilot, but it has been so heavily modified and extended
# that I don't think much of the copilot code remains.
#
# The really difficult issues boil down to two areas:
# 1. The PDF extraction process. The PDF library is pretty good at extracting text, but
#    it's a little tricky to stitch together lines that are hyphenated! I have a bunch of
#    heuristics that try to get close, but there are really subtle issues like MGTBench
#    getting hyphenated at the MGT. And ZooKeeper getting hyphenated to Zoo.
# 2. The bibliographic references are often really badly formatted. I have a bunch of heuristics
#    that try to get the title, year, and author list out of the reference, but it's tricky.
# 3. OpenAlex is picky about the symbols in the title. : is a no go as well as , but should
#    they be ignored or replaced by a space. I found you need to keep the . :)

import logging
import os
import unicodedata
from collections import namedtuple
from datetime import datetime

import arxiv
import click
from pyalex import Works
from pymupdf import TEXT_MEDIABOX_CLIP, TEXT_CID_FOR_UNKNOWN_UNICODE

EXTRACTION_FLAGS = TEXT_MEDIABOX_CLIP | TEXT_CID_FOR_UNKNOWN_UNICODE

CURRENT_YEAR = datetime.now().year
from os.path import isdir

import fitz  # PyMuPDF
import re
import requests
import enchant

DOI_ORG_PREFIX = "https://doi.org/"

DOI_ORG_API = "https://doi.org/api/handles/"

URL_PATTERN = re.compile(r'https?:(//\S*)? ?$')

WORDS = enchant.Dict("en_US")


def _strip_prefix(s: str, prefix: str) -> str:
    return s[len(prefix):] if s.startswith(prefix) else s


# This massively gross hack (which totally works) is brought to
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


# This class will be fed one character at a time and will return true if the current character is
# part of a URL
class URLTracker:
    HTTP_PREFIX = "http://"
    HTTPS_PREFIX = "https://"

    def __init__(self):
        self.match_index = 0

    def in_url(self):
        return self.match_index >= 7  # we've matched up to http://

    def add_char(self, c):
        if c.isspace():
            self.match_index = 0
        elif self.match_index < 7:
            if c == self.HTTP_PREFIX[self.match_index] or c == self.HTTPS_PREFIX[self.match_index]:
                self.match_index += 1
            else:
                self.match_index = 1 if c == "h" else 0


def fix_accents(text):
    converted = ''
    accent = None
    url_tracker = URLTracker()
    for char in text:
        url_tracker.add_char(char)
        if accent:
            converted += unicodedata.normalize("NFC", char + accent)
            accent = None
        else:
            if url_tracker.in_url():
                # the PDF parser (or the author) may have a mangled tilde
                character_name = unicodedata.name(char).lower()
                if "tilde" in character_name:
                    char = "~"
            else:
                # we don't look for accents in URLs
                accent = make_combining_form(char) if not url_tracker.in_url() else None
            if not accent:
                converted += char
    return converted


# remove all accents and non alpha characters from a string
# we did all that work above and now we are going to undo it for comparisons
def just_the_chars(text, space_ok=False, numbers_ok=False):
    alphatext = ''
    for c in unicodedata.normalize("NFD", text):
        if (unicodedata.category(c)[0] == 'L' or (space_ok and c.isspace()) or (
                numbers_ok and (c.isdigit() or c in ['.']))):
            alphatext += c
        elif space_ok:
            alphatext += ' '
    return alphatext


# bounding box is a tuple of (top_left_x, top_left_y, bottom_right_x, bottom_right_y)
# we are going to assume that the text is in a single line if the y coordinates overlap
def on_same_line(prev_bb, bb):
    if not prev_bb:
        return True
    prev_y_top = prev_bb[1]
    prev_y_bottom = prev_bb[3]
    bb_y_top = bb[1]
    bb_y_bottom = bb[3]
    return prev_y_top < bb_y_bottom and prev_y_bottom > bb_y_top


# we are going to assume that the text is touching if the x coordinates overlap
def bb_touching(prev_bb, bb):
    if not prev_bb:
        return True
    prev_x_left = prev_bb[0]
    prev_x_right = prev_bb[2]
    bb_x_left = bb[0]
    bb_x_right = bb[2]
    # provide 0.5 margin for error
    return prev_x_right + 0.5 > bb_x_left


def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ''

    for page in doc:
        # we need more sophisticated processing than get_text to preserve lines
        text_page = page.get_textpage(flags=EXTRACTION_FLAGS)
        prev_bb = None
        for text_block in text_page.extractDICT()['blocks']:
            for line in text_block['lines']:
                for span in line['spans']:
                    bb = span['bbox']
                    if on_same_line(prev_bb, bb):
                        delimiter = '' if bb_touching(prev_bb, bb) else ' '
                        text += delimiter + span['text']
                    else:
                        yield text
                        text = span['text']
                    prev_bb = bb

    # if there is anything else left, return it
    if text:
        yield text


def extract_references(text_lines):
    # Roughly extract references section
    for line in text_lines:
        references_section = re.search(r'(references|bibliography)\s*$', line.strip(), flags=re.IGNORECASE)
        if references_section:
            break
    ref = None
    for line in text_lines:
        if line.lstrip().startswith("["):
            if ref:
                yield fix_accents(ref)
            ref = line.lstrip()
            continue
        if ref:
            # if we have a line break in the middle of a URL we don't want to add a space
            if URL_PATTERN.search(ref):
                # this is probably the . at the end of the URL
                if line:
                    if (ref.endswith(".") or ref.endswith(". ")) and line[0].isupper():
                        ref = ref + " " + line
                    else:
                        ref = ref.rstrip() + line
            else:
                # fix any hyphenated lines
                if ref.endswith("-"):
                    ref = decide_on_hyphen(ref, line)
                else:
                    ref += " " + line
    if ref:
        yield fix_accents(ref)


def check_dictionary(word):
    # super big hack. words like gaussian are only valid if capitalized, and AI
    # is in the dictionary but authors who don't know how to do bibliographies often get AI rendered as Ai
    return WORDS.check(word) or WORDS.check(word.upper())


def decide_on_hyphen(ref, line):
    # get the last word from ref and the first word from line
    first_word_match = re.search(r'(\w+)-$', ref)
    first_word = first_word_match.group(1) if first_word_match else None
    last_word_match = re.search(r'\w+', line)
    last_word = last_word_match.group() if last_word_match else None
    if first_word and not first_word.isalpha():
        first_word = None
    if last_word and not last_word.isalpha():
        last_word = None
    if not first_word or not last_word or last_word[0].isupper():
        # these aren't words so preserve the hyphen or
        # if the last word is capitalized (probably a name) preserve the hyphen
        ref = ref + line
    elif check_dictionary(first_word + last_word):
        # if the first and last words are a valid word, remove hyphen
        ref = ref[:-1] + line
    elif check_dictionary(first_word) and check_dictionary(last_word):
        # keep the hyphen between two valid words
        ref = ref + line
    else:
        # we don't have valid words, so remove the hyphen
        ref = ref[:-1] + line
    return ref


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
        logging.debug(f"Checking URL: {url} returned status code: {response.status_code}")
        # we are going to take 403 as meaning that it could be there...
        return response.status_code < 400 or response.status_code == 403
    except requests.RequestException as ex:
        logging.debug(f"Checking URL: {url} caused exception: {ex}")
        return False


BibResult = namedtuple('BibResult', ['title', 'year', 'author', 'venue', 'is_retracted'])

OPENALEX_API = "https://api.openalex.org/works"


def alphanum_spaces_only(title):
    # we are going to strip out all the accents and non-alpha characters
    # and then compare the two strings
    return just_the_chars(title, space_ok=True, numbers_ok=True)


def search_openalex(title):
    no_symbol_title = alphanum_spaces_only(title)
    try:
        logging.debug(f"Searching OpenAlex for: {no_symbol_title}")
        retracted = []
        not_retracted = []
        for work in Works().search_filter(title=f'"{no_symbol_title}"').get():
            is_retracted = work['is_retracted']
            result_title = work['title']
            logging.debug(f"Found OpenAlex title: {result_title}")
            if not result_title or not (  # we want to return the title if it matches or if it is a retracted paper
                    is_retracted or "retracted" in result_title.lower() or result_title_compare(result_title, title)):
                continue
            result_year = str(work['publication_year'])
            result_authors = [author['author']['display_name'] for author in work['authorships']]
            result_primary_location = work['primary_location']
            result_primary_location_source = result_primary_location['source'] if result_primary_location else None
            result_primary_location_name = result_primary_location_source[
                'display_name'] if result_primary_location_source else None

            bib_result = BibResult(result_title, result_year, result_authors, result_primary_location_name,
                                   is_retracted)
            if is_retracted:
                retracted.append(bib_result)
            else:
                not_retracted.append(bib_result)

        # yield the retracted papers first
        for result in retracted:
            yield result

        for result in not_retracted:
            yield result
    except Exception as ex:
        logging.error(f"Error fetching OpenAlex data for {title}: {ex}")


def result_title_compare(result_title, title):
    # we are going to strip out all the accents and non-alpha characters
    # and then compare the two strings
    return just_the_chars(result_title.lower()) == just_the_chars(title.lower())


def search_arxiv(title):
    try:
        client = arxiv.Client()
        logging.debug(f"Searching arXiv for: {title}")
        search = arxiv.Search(query=f"ti:{title}", max_results=10, sort_by=arxiv.SortCriterion.Relevance)

        for result in client.results(search):
            result_title = result.title
            is_retracted = "withdrawn" in result.comment.lower() if result.comment else False
            logging.debug(f"arXiv title: {result_title}")
            if not result_title or not result_title_compare(result_title, title):
                continue
            result_year = str(result.published.year)
            result_authors = [author.name for author in result.authors]
            yield BibResult(result_title, result_year, result_authors, "arXiv", is_retracted)
    except Exception as ex:
        logging.error(f"Error fetching arXiv data for {title}: {ex}")


def search_for_title(title, arxiv_search=False):
    openalex_results = search_openalex(title)
    for result in openalex_results:
        yield result

    if arxiv_search:
        arxiv_results = search_arxiv(title)
        for result in arxiv_results:
            yield result


def normalize_quotes(ref: str) -> str:
    # Define a dictionary of different double quote characters to replace
    quote_replacements = {'“': '"', '”': '"', '„': '"', '‟': '"', '«': '"', '»': '"'}

    # Replace each quote character in the dictionary with the standard double quote
    for old_quote, new_quote in quote_replacements.items():
        ref = ref.replace(old_quote, new_quote)
    return ref


def extract_possible_title(start_of_title):
    # get the reference without the authors
    start_of_title = start_of_title[find_end_of_authors(start_of_title):].strip()
    # if there is a (, the authors are using a format that has a date before the title
    if start_of_title.startswith("("):
        end_paren = start_of_title.find(")")
        # there may be a comma or period after the )
        if start_of_title[end_paren + 1] != " ":
            end_paren += 1
        start_of_title = start_of_title[end_paren + 1:].strip()

    if start_of_title.startswith('"'):
        # we have a quoted title
        end_quote = start_of_title.find('"', 1)
        while start_of_title[end_quote - 1].isspace():
            # titles with embedded quotes are the worst!
            end_inner_quote = start_of_title.find('"', end_quote + 1)
            end_quote = start_of_title.find('"', end_inner_quote + 1)

        # we add 2 to end_quote to skip the " and punctuation after it
        return start_of_title[1:end_quote].rstrip(",").rstrip(".").strip(), start_of_title[end_quote + 2:].strip()
    else:
        # we don't have a quoted title, so we look for the first period
        period = start_of_title.find(". ")
        return (start_of_title[:period].strip(), start_of_title[period + 1:].strip())


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


def looks_like_an_initial(ref, period_position):
    if ref[period_position - 1].isupper():
        look_back = period_position - 1
        while look_back > 0 and ref[look_back].isupper():
            look_back -= 1
        if look_back == 0:
            # we got to the beginning of the line, it is definitely an initial
            return True

        # skip any leading spaces
        while look_back > 0 and ref[look_back].isspace():
            look_back -= 1

        if look_back == 0 or ref[look_back] in [',', ']']:
            # we are at the beginning of the reference or the comma separating us from a previous author
            return True

        # 4 seems arbitrary and small, but we need to make sure there is something to look at...
        if look_back > 4 and ref[look_back] == ".":
            return looks_like_an_initial(ref, look_back)

        if look_back > 2 and ref[look_back - 2:look_back + 1] == "and":
            return True

        return False


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

        # check if we are actually a leading initial
        if looks_like_an_initial(ref, period):
            continue

        # move period past the ". "
        period += 2
        # a hack to make sure we didn't get stuck on a trailing initial.
        # if the next ". " also precedes a capital letter, we are not at the end of the authors
        next_period = ref.find(". ", period)
        if next_period != -1 and ref[next_period - 1].isupper():
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
    author_list = re.sub(r'^\[\d+]\s*', '', author_list)
    # We are assuming the biggest part of the name is the last name
    raw_author_split = re.split(", | and ", author_list)
    author_last_names = []
    for author in raw_author_split:
        author = author.strip()
        if not author:
            continue
        # looks like we hit a date
        if re.search(r'\d', author):
            break
        # Remove any initials or periods from the name
        name_parts = [n for n in author.split(' ') if
                      len(n) > 1 and '.' not in n and n[0].isupper() and not n.isupper()]
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


def check_references_validity(references, only_link_check, strict_title):
    sketchy = []
    for ref in references:
        links = find_urls_or_dois(ref)
        sketchy_problem = []

        if links:
            bad_links = [url for url in links if not check_url_validity(url)]
            if bad_links:
                sketchy_problem.append("❌ Invalid DOI or URL: " + ", ".join(bad_links))
            else:
                sketchy_problem.append(f"✅ All links are valid: {', '.join(links)}")

        (title, after_title) = extract_possible_title(ref)
        year = extract_possible_year(after_title)
        authors = extract_possible_author_last_names(ref)

        # filter out parts that are URL related
        published_somewhere = [x for x in after_title.split(". ") if (
                x and "accessed" not in x.lower() and "retrieved" not in x.lower() and x[
            0].isalpha() and not x.lower().startswith("url") and not x.lower().startswith("http"))]

        if not published_somewhere:
            if links:
                sketchy_problem.append("👉 No venue info, so only checking links")
            else:
                sketchy_problem.append("❌ No venue info or links, this reference looks bogus")

        if published_somewhere and not only_link_check:
            found_title = False
            year_problem = None  # this means it's not set. '' means year was good
            missing_authors = []
            for search_result in search_for_title(title, arxiv_search="arxiv" in ref.lower()):
                # accents and other characters that might vary
                item_authors = [just_the_chars(x) for x in search_result.author]
                found_title = True
                if search_result.is_retracted:
                    sketchy_problem.append("☣️ This paper is retracted!")
                if strict_title:
                    if search_result.title != title:
                        sketchy_problem.append(f"⚠️ Title not exact: found '{search_result.title}' != '{title}'")
                if year and year_problem != '' and search_result.year:
                    if search_result.year == str(year):
                        year_problem = ''
                    else:
                        year_problem = f'❌ found year {search_result.year} but looking for {year}'
                missing_authors = find_missing_authors(authors, item_authors)
                if (not year or year_problem == '') and not missing_authors:
                    break

            if not found_title:
                sketchy_problem.append(f"❌ Title not found: {title}")
            else:
                sketchy_problem.append(f"✅ Found title: {title}")
                if not year:
                    sketchy_problem.append("☣️ Publication year missing from reference")
                elif year_problem:
                    sketchy_problem.append(year_problem)
                else:
                    sketchy_problem.append(f"✅ Found year: {year}")
                if missing_authors:
                    sketchy_problem.append("❌ Missing authors: " + ", ".join(missing_authors))
                else:
                    sketchy_problem.append(f"✅ Authors are consistent")

        if sketchy_problem:
            sketchy.append((ref, sketchy_problem))
    return sketchy


@click.command()
@click.argument('pdf_path', type=click.Path(exists=True))
@click.option('--dump-info', is_flag=True, default=False, help='Just dumpe the info gleaned from the PDF')
@click.option('--only-link-check', is_flag=True, default=False, help='Only check the validity of the links')
@click.option('--debug', is_flag=True, default=False, help='Show requests and responses from network')
@click.option('--strict-title', is_flag=True, default=False, help='Do a strict comparison of the title')
@click.option('--problems-only', is_flag=True, default=False, help='Only show problems')
def main(pdf_path, dump_info, only_link_check, debug, strict_title, problems_only):
    """
    Check the references in PDF files for validity using OpenAlex, arXiv, and URL checking.

    PDF_PATH can be a directory or a file. if it is a directory, all the PDFs in the directory will be checked.
    """
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    if isdir(pdf_path):
        pdfs = []
        for root, dirs, files in os.walk(pdf_path):
            for file in [os.path.join(root, f) for f in files if f.endswith('.pdf')]:
                pdfs.append(file)
        # sort them so that numerical order is preserved (assuming the numbers are less than 1,000,000
        for file in sorted(pdfs, key=lambda x: os.path.sep.join(
                [p.zfill(6) if p.isdigit() else p for p in x.split(os.path.sep)])):
            check_references(file, dump_info, only_link_check, strict_title=strict_title, problems_only=problems_only)
            print("-----------------------------\n")
    else:
        check_references(pdf_path, dump_info, only_link_check, strict_title=strict_title, problems_only=problems_only)


def extract_info(references):
    for ref in references:
        links = find_urls_or_dois(ref)
        authors = extract_possible_author_last_names(ref)
        (title, after_title) = extract_possible_title(ref)
        year = extract_possible_year(after_title)
        print(f"('{ref}'\n{year}, {authors}, '{title}')\n")


def sanitize_ref(ref):
    ref = normalize_quotes(ref)
    # we get double spaces when line justification happens sometimes. remove them
    while "  " in ref:
        ref = ref.replace("  ", " ")
    return ref


def check_references(pdf_path, dump_info, only_link_check, strict_title, problems_only):
    print(f"Extracting references from: {pdf_path}")
    text_lines = extract_text_from_pdf(pdf_path)
    references = [sanitize_ref(x) for x in extract_references(text_lines)]
    print(f"Found {len(references)} references.\n")
    if dump_info:
        extract_info(references)
    else:
        sketchy = check_references_validity(references, only_link_check, strict_title=strict_title)

        if sketchy:
            for (ref, sketchy_problems) in sketchy:

                if problems_only:
                    sketchy_problems = [p for p in sketchy_problems if p[0] != "✅" and p[0] != "👉"]
                if not sketchy_problems:
                    continue
                print(f"=> {ref}")
                for sketchy_problem in sketchy_problems:
                    print(f"  {sketchy_problem}")
        print()


if __name__ == "__main__":
    main()
