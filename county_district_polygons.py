import csv
import os
import sys
import ujson as json
from collections import defaultdict
from shapely.geometry import shape
from shapely.geometry.geo import mapping

FRRC_DATA_DIR = 'data/'

FL_CONGRESSIONAL_DISTRICTS_FILENAME = 'fl_congressional_districts.geojson'
FL_COUNTIES_FILENAME = 'fl_counties.geojson'
FL_COUNTY_DISTRICTS_FILENAME = 'fl_county_district_petitions.geojson'
FL_DISTRICT_PETITIONS_FILENAME = 'fl_district_petitions.geojson'

DISTRICT_PETITIONS_FILENAME = 'petitions.tsv'
COUNTY_DISTRICTS_FILENAME = 'county_by_district_petitions.tsv'

COUNTY_DISTRICT_DEM_VOTE_FILENAME = 'fl_county_district_dem_vote_share_2016.tsv'


def build_district_dem_votes(county_district_dem_votes):
    district_dem_votes = defaultdict(int)
    for (county, district), props in county_district_dem_votes.items():
        district_dem_votes[district] += int(props['Dem Votes 2016'])
    return dict(district_dem_votes)


def build_county_dem_votes(county_district_dem_votes):
    county_dem_votes = defaultdict(int)
    for (county, district), props in county_district_dem_votes.items():
        county_dem_votes[county] += int(props['Dem Votes 2016'])
    return dict(county_dem_votes)


def build_single_district_counties(county_district_dem_votes):
    district_counties = defaultdict(set)
    for (county, district) in list(county_district_dem_votes):
        district_counties[county].add(district)
    return {k: list(v)[0] for k, v in district_counties.items() if len(v) == 1}


def build_county_district_dem_vote_share(county_district_dem_votes_filename):
    reader = csv.reader(open(county_district_dem_votes_filename), delimiter='\t')
    county_district_dem_votes = {}
    headers = reader.next()
    for row in reader:
        county, district, dem, gop, total, pct_dem, county_share_dem = list(range(len(headers)))
        row_kvs = {
            headers[dem]: int(row[dem]),
            headers[gop]: int(row[gop]),
            headers[total]: int(row[total]),
            headers[pct_dem]: float(row[pct_dem]),
            headers[county_share_dem]: float(row[county_share_dem]),
        }

        county_district_dem_votes[(row[county], row[district])] = row_kvs
    return county_district_dem_votes


def county_district_petitions(county_districts_filename):
    reader = csv.reader(open(county_districts_filename), delimiter='\t')
    valid = {}
    headers = reader.next()
    for row in reader:
        county, district, as_of, valid_signatures, valid_in_county, valid_in_district, needed_in_district = list(range(len(headers)))
        row_kvs = {
            headers[as_of]: row[as_of],
            headers[valid_signatures]: int(row[valid_signatures]),
            headers[valid_in_county]: int(row[valid_in_county]),
            headers[valid_in_district]: int(row[valid_in_district]),
            headers[needed_in_district]: int(row[needed_in_district]),
        }

        valid[(row[county], row[district])] = row_kvs
    return valid


def district_petitions(county_districts_filename):
    reader = csv.reader(open(county_districts_filename), delimiter='\t')
    districts = {}
    headers = reader.next()
    for row in reader:
        district, valid_signatures, needed_for_ballot, remaining, least_recent, most_recent = list(range(len(headers)))
        row_kvs = {
            headers[district]: row[district],
            headers[valid_signatures]: int(row[valid_signatures]),
            headers[needed_for_ballot]: int(row[needed_for_ballot]),
            headers[remaining]: int(row[remaining]),
            headers[least_recent]: row[least_recent],
            headers[most_recent]: row[most_recent],
        }

        districts[row[district]] = row_kvs
    return districts


def create_district_petition_features(district_features, districts):
    district_petition_features = []
    for f_orig in district_features['features']:
        f = f_orig.copy()
        props = f['properties']
        district = props['CD115FP']
        props = districts[district]
        f['properties'] = props
        district_petition_features.append(f)
    return district_petition_features


def create_county_district_features(county_features, district_features, valid_county_districts, county_district_dem_votes):
    county_polys = [shape(county['geometry']) for county in county_features['features']]

    district_polys = [shape(district['geometry']) for district in district_features['features']]

    county_district_features = []

    district_dem_votes = build_district_dem_votes(county_district_dem_votes)
    county_dem_votes = build_county_dem_votes(county_district_dem_votes)
    single_district_counties = build_single_district_counties(county_district_dem_votes)

    # Not a huge number of comparisons, naive method is fine
    for i, county_poly in enumerate(county_polys):
        for j, district_poly in enumerate(district_polys):
            district = district_features['features'][j]['properties']['CD115FP']
            county = county_features['features'][i]['properties']['NAME']
            if (county, district) not in valid_county_districts:
                continue

            if district_poly.contains(county_poly):
                geom = county_poly
            elif district_poly.intersects(county_poly) and not district_poly.touches(county_poly):
                geom = district_poly.intersection(county_poly)
                if geom.type not in ('Polygon', 'MultiPolygon'):
                    buffered = geom.buffer(0.0)
                    if not buffered.is_valid:
                        continue
                    geom = buffered
                    if geom.type not in ('Polygon', 'MultiPolygon'):
                        continue
            else:
                continue

            district = district_features['features'][j]['properties']['CD115FP']
            county = county_features['features'][i]['properties']['NAME']

            props = {'district': district,
                     'county': county}

            county_district_signatures = valid_county_districts[(county, district)]

            props.update(county_district_signatures)

            valid_signatures = int(county_district_signatures['Valid Signatures'])

            dem_votes = county_district_dem_votes.get((county, district), {})
            if not dem_votes and county in single_district_counties:
                dem_votes = county_district_dem_votes.get((county, single_district_counties[county]), {})

            if dem_votes:
                dem_votes_approx = int(dem_votes['Dem Votes 2016'])
                expected_county_share_of_signatures = float(dem_votes['County Share of Dem Votes in District'])
                expected_county_share_method = '2016 Election Precinct Results'
            else:
                num_dem_votes_in_county = county_dem_votes[county]
                num_dem_votes_in_district = district_dem_votes[district]
                valid_in_county = int(county_district_signatures['Total Valid Signatures in County'])
                valid_in_county_district = valid_signatures
                if valid_in_county > 0:
                    dem_votes_approx = num_dem_votes_in_county * (valid_in_county_district / float(valid_in_county))
                else:
                    dem_votes_approx = 0
                expected_county_share_of_signatures = dem_votes_approx / num_dem_votes_in_district
                expected_county_share_method = 'Share of Signatures in County Split'

            props['Dem Votes 2016'] = dem_votes_approx
            props['Expected County Share of Dems in District'] = expected_county_share_of_signatures
            props['Expected County Share Method'] = expected_county_share_method

            total_valid_in_district = int(county_district_signatures['Total Valid Signatures in District'])
            total_needed = int(county_district_signatures['Total Needed in District'])
            expected = int(expected_county_share_of_signatures * total_needed)
            if total_needed < total_valid_in_district:
                expected = min(expected, valid_signatures)
            props['Expected Signatures'] = int(expected)
            props['Expected Signatures Remaining'] = max(expected - valid_signatures, 0) if total_needed > total_valid_in_district else 0

            try:
                geom_mapping = mapping(geom)
            except Exception:
                continue

            county_district_features.append({
                'type': 'Feature',
                'geometry': geom_mapping,
                'properties': props
            })

    return county_district_features


def create_county_districts_geojson(data_dir=FRRC_DATA_DIR):
    valid_county_districts = county_district_petitions(os.path.join(data_dir, COUNTY_DISTRICTS_FILENAME))

    districts = district_petitions(os.path.join(data_dir, DISTRICT_PETITIONS_FILENAME))
    county_district_dem_votes = build_county_district_dem_vote_share(os.path.join(data_dir, COUNTY_DISTRICT_DEM_VOTE_FILENAME))

    county_features = json.load(open(os.path.join(data_dir, FL_COUNTIES_FILENAME)))
    district_features = json.load(open(os.path.join(data_dir, FL_CONGRESSIONAL_DISTRICTS_FILENAME)))
    county_district_features = create_county_district_features(county_features, district_features, valid_county_districts, county_district_dem_votes)
    out = open(os.path.join(data_dir, FL_COUNTY_DISTRICTS_FILENAME), 'w')
    json.dump({'type': 'FeatureCollection', 'features': county_district_features}, out)

    district_petition_features = create_district_petition_features(district_features, districts)
    out = open(os.path.join(data_dir, FL_DISTRICT_PETITIONS_FILENAME), 'w')
    json.dump({'type': 'FeatureCollection', 'features': district_petition_features}, out)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        data_dir = sys.argv[0]
    else:
        data_dir = FRRC_DATA_DIR
    create_county_districts_geojson(data_dir=data_dir)
