import csv
import lxml.html
import os
import re
import requests

from collections import Counter

OFFICIAL_COUNTS_URL = 'http://dos.elections.myflorida.com/initiatives/initSignDetailCounty.asp?account=64388&seqnum=1&ctype=CSV&elecyear=2018'
FRRC_DATA_DIR = 'data'
COUNTY_PETITIONS_FILE = 'county_petitions.tsv'
PETITIONS_FILE = 'petitions.tsv'
COUNTY_AND_DISTRICT_PETITIONS_FILE = 'county_by_district_petitions.tsv'

county_name_regex = re.compile('^\s*(?:(?:[\w]+[\.]?)(?:[\-][\w]+[\.]?)*\s*)+')
date_regex = re.compile('\(\s*as of ([\d]{2}/\d{2}/\d{4})\s*\)', re.I)

html_whitespace_regex = re.compile('(?:\s+|(?:&nbsp;)+)')
number_regex = re.compile('[\d,]+')

district_regex = re.compile('DISTRICT\s*[\d]+', re.I)
needed_for_review_regex = re.compile('Needed for Review\s*([\d,]+)', re.I)
needed_for_ballot_regex = re.compile('Needed for Ballot\s*([\d,]+)', re.I)


def cleanup_whitespace(text):
    return html_whitespace_regex.sub(u' ', text).strip()


def cleanup_text_element(tree):
    for el in tree:
        if el.tag == 'br':
            el.tail = u'\n' + el.tail
            el.drop_tree()
        else:
            el.text = cleanup_whitespace(el.text)


class CountyPetitions(object):
    def __init__(self, name, petitions, as_of_date=None):
        self.name = name
        self.petitions = petitions
        self.as_of_date = as_of_date


class DistrictPetitions(object):
    def __init__(self, name, needed_for_review, needed_for_ballot):
        self.name = name
        self.needed_for_review = needed_for_review
        self.needed_for_ballot = needed_for_ballot
        self.counties = []

    def add_county(self, county):
        self.counties.append(county)

    @property
    def total_petitions(self):
        return sum((c.petitions for c in self.counties))


def extract_petition_data(html):
    districts = []
    for table in html.xpath('//table'):
        center = table.getprevious()
        if center is None or not len(center):
            continue

        cleanup_text_element(center)
        heading = [s.strip() for s in center.text_content().split(u'\n') if s.strip()]

        district_name = None
        needed_for_review = None
        needed_for_ballot = None

        for line in heading:
            if district_regex.match(line):
                district_name = line
            else:
                review_match = needed_for_review_regex.match(line)
                if review_match:
                    needed_for_review = int(review_match.group(1).replace(u',', u''))
                else:
                    ballot_match = needed_for_ballot_regex.match(line)
                    if ballot_match:
                        needed_for_ballot = int(ballot_match.group(1).replace(u',', u''))

        district = DistrictPetitions(district_name, needed_for_review, needed_for_ballot)

        rows = table.xpath('tr')
        num_rows = len(rows)

        for i, row in enumerate(rows):
            columns = row.xpath('td')

            county_cell = cleanup_whitespace(columns[0].text_content()).strip()

            name_match = county_name_regex.match(county_cell)
            if not name_match:
                continue

            name = name_match.group(0)

            date_match = date_regex.search(county_cell)
            as_of_date = None
            if date_match:
                as_of_date = date_match.group(1)

            if i == 0 and name.upper() == u'COUNTY':
                continue
            elif i == num_rows - 1 and name.upper() == u'TOTAL':
                continue

            petitions = int(number_regex.match(columns[1].text).group(0).strip().replace(u',', u''))
            county = CountyPetitions(name, petitions, as_of_date)
            district.add_county(county)

        districts.append(district)
    return districts


def scrape_signature_counts(url=OFFICIAL_COUNTS_URL, out_dir=FRRC_DATA_DIR, petitions_file=PETITIONS_FILE, county_petitions_file=COUNTY_PETITIONS_FILE, county_and_district_petitions_file=COUNTY_AND_DISTRICT_PETITIONS_FILE):
    response = requests.get(url)
    html = lxml.html.fromstring(response.content)

    districts = extract_petition_data(html)

    f = open(os.path.join(out_dir, petitions_file), 'w')
    writer = csv.writer(f, delimiter='\t')

    petition_headers = ['District', 'Valid Signatures', 'Needed for Ballot']
    writer.writerow(petition_headers)

    totals_by_district = [(d.name, d.total_petitions, d.needed_for_ballot) for d in districts]

    writer.writerows(totals_by_district)

    f.close()

    totals_by_county = Counter()
    for d in districts:
        for c in d.counties:
            totals_by_county[c.name] += c.petitions

    f = open(os.path.join(out_dir, county_petitions_file), 'w')
    writer = csv.writer(f, delimiter='\t')

    county_headers = ['County', 'Valid Signatures']
    writer.writerow(county_headers)

    writer.writerows(sorted(totals_by_county.most_common()))

    f = open(os.path.join(out_dir, county_and_district_petitions_file), 'w')
    writer = csv.writer(f, delimiter='\t')

    county_district_headers = ['County', 'District', 'As Of', 'Valid Signatures', 'Total Valid Signatures in County', 'Total Valid Signatures in District', 'Total Needed in District']

    writer.writerow(county_district_headers)
    writer.writerows(sorted([(c.name, d.name, c.as_of_date or '', c.petitions, totals_by_county[c.name], d.total_petitions, d.needed_for_ballot) for d in districts for c in d.counties]))

if __name__ == '__main__':
    scrape_signature_counts()
