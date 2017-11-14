FRRC_DATA_DIR=./data/
DISTRICTS_ZIP_FILENAME=cb_2016_us_cd115_500k.zip
DISTRICTS_SHAPEFILE_URL=http://www2.census.gov/geo/tiger/GENZ2016/shp/$DISTRICTS_ZIP_FILENAME
DISTRICTS_SHAPEFILE_NAME=cb_2016_us_cd115_500k.shp
DISTRICTS_OUT_FILENAME=fl_congressional_districts.geojson

COUNTY_ZIP_FILENAME=cb_2016_us_county_500k.zip
COUNTY_SHAPEFILE_URL=http://www2.census.gov/geo/tiger/GENZ2016/shp/$COUNTY_ZIP_FILENAME
COUNTY_SHAPEFILE_NAME=cb_2016_us_county_500k.shp
COUNTY_OUT_FILENAME=fl_counties.geojson

FLORIDA_FIPS_CODE=12

COUNTY_AND_DISTRICT_SHAPEFILE_NAME=fl_districts_and_counties.shp
COUNTY_AND_DISTRICT_OUT_FILENAME=fl_districts_and_counties.geojson

convert_to_geojson() {
    filename=$1
    out_filename=$2

}


download_and_unzip_shapefile() {
    url=$1
    filename=$2
    dest_dir=$3

    mkdir -p $dest_dir
    cd $dest_dir

    wget $url -O $filename
    unzip $filename

    cd -
}


TEMP_DIR=$(mktemp -d)

mkdir -p $TEMP_DIR
download_and_unzip_shapefile $DISTRICTS_SHAPEFILE_URL $DISTRICTS_ZIP_FILENAME $TEMP_DIR

rm -f $FRRC_DATA_DIR/$DISTRICTS_OUT_FILENAME
ogr2ogr -f GeoJSON -t_srs EPSG:4326 -where "STATEFP='$FLORIDA_FIPS_CODE'" $FRRC_DATA_DIR/$DISTRICTS_OUT_FILENAME $TEMP_DIR/$DISTRICTS_SHAPEFILE_NAME

download_and_unzip_shapefile $COUNTY_SHAPEFILE_URL $COUNTY_ZIP_FILENAME $TEMP_DIR

rm -f $FRRC_DATA_DIR/$COUNTY_OUT_FILENAME
ogr2ogr -f GeoJSON -t_srs EPSG:4326 -where "STATEFP='$FLORIDA_FIPS_CODE'" $FRRC_DATA_DIR/$COUNTY_OUT_FILENAME $TEMP_DIR/$COUNTY_SHAPEFILE_NAME

rm -rf $TEMP_DIR
