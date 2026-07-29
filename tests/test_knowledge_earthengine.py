from stratigraphic_amenity.knowledge import Bounds, KnowledgeRequest
from stratigraphic_amenity.knowledge.providers.earthengine import (
    EarthEngineLandcoverProvider,
    EarthEnginePopulationDensityProvider,
)


class FakeInfoValue:
    def __init__(self, value):
        self.value = value

    def getInfo(self):
        return self.value


class FakeReduceResult:
    def __init__(self, values):
        self.values = values

    def get(self, key):
        return FakeInfoValue(self.values[key])


class FakeImage:
    def __init__(self, reduce_values):
        self.reduce_values = reduce_values

    def mosaic(self):
        return self

    def clip(self, region):
        return self

    def reduceRegion(self, **kwargs):
        return FakeReduceResult(self.reduce_values)


class FakeRegion:
    def area(self):
        return FakeInfoValue(2_000_000)


class FakeGeometry:
    @staticmethod
    def Rectangle(bounds):
        return FakeRegion()


class FakeReducer:
    @staticmethod
    def frequencyHistogram():
        return "frequencyHistogram"

    @staticmethod
    def sum():
        return "sum"


class FakeEarthEngine:
    Geometry = FakeGeometry
    Reducer = FakeReducer

    def __init__(self, reduce_values):
        self.reduce_values = reduce_values
        self.initialized_projects = []

    def Initialize(self, project=None):
        self.initialized_projects.append(project)

    def ImageCollection(self, dataset_id):
        return FakeImage(self.reduce_values)


def test_earthengine_providers_initialize_project_and_shape_results():
    scenarios = (
        (
            EarthEngineLandcoverProvider,
            {"Map": {"10.0": 3, "20.0": 1}},
            "landcover_distribution",
            {"Trees": 75.0, "Shrubland": 25.0},
            2,
        ),
        (
            EarthEnginePopulationDensityProvider,
            {"population": 1000},
            "population_density",
            {
                "population_total": 1000,
                "area_km2": 2.0,
                "density_people_per_km2": 500.0,
                "label": "500.0 people/km^2",
            },
            1,
        ),
    )

    for provider_type, reduce_values, expected_key, expected_value, expected_count in scenarios:
        fake_ee = FakeEarthEngine(reduce_values)
        provider = provider_type(ee_module=fake_ee, project="test-project")

        item = provider.query(
            KnowledgeRequest(bounds=Bounds(min_lon=-1, min_lat=1, max_lon=2, max_lat=3))
        )[0]

        assert fake_ee.initialized_projects == ["test-project"]
        assert item.key == expected_key
        assert item.value == expected_value
        assert item.record_count == expected_count
