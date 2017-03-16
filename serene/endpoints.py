"""
Copyright (C) 2017 Data61 CSIRO
Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

Endpoint objects for the user to view and manipulate. These wrap around
server Session objects and call methods to talk to the server.
"""
import collections
import os
import tempfile
from functools import lru_cache

import pandas as pd

from serene.elements.dataset import DataSet
from serene.elements import Ontology
from serene.elements import SSD
from .elements.octopus import Octopus
from .matcher.model import Model
from .utils import flatten, gen_id


def decache(func):
    """
    Decorator for clearing the cache. Here we explicitly mark the
    caches that need clearing. There may be a more elegant way to
    do this by having a new lru_cache wrapper that adds the functions
    to a global store, and the cache busters simply clear from this
    list.
    """
    def wrapper(self, *args, **kwargs):
        """
        Wrapper function that busts the cache for each lru_cache file
        """
        if not issubclass(type(self), IdentifiableEndpoint):
            raise ValueError("Can only clear cache of IdentifiableEnpoint class")

        type(self).items.fget.cache_clear()

        return func(self, *args, **kwargs)
    return wrapper


class IdentifiableEndpoint(object):
    """
    An endpoint object that can view and manipulate objects on the server.
    Each object must have a key to identify.
    """
    def __init__(self):
        """
        Only a base type needs to be specified on init, which has to
        contain an `id` variable of type int
        """
        # this is the type of the stored objects
        self._base_type = None

    def _apply(self, func, value, func_name=None):
        """
        Helper function to call `func` with parameter `value` which
        can be an object or an integer key

        :param func: The function to be called
        :param value: An int key or the local object
        :param func_name: A string to use for debugging (optional)
        :return:
        """
        if type(value) == int:
            return func(value)
        elif issubclass(type(value), self._base_type):
            return func(value.id)
        else:
            if func_name is None:
                msg = "Illegal type found: {}".format(type(value))
            else:
                msg = "Illegal type found in {}: {}".format(func_name, type(value))
            raise TypeError(msg)

    @property
    def items(self):
        return tuple()


class ReadOnlyDict(collections.Mapping):

    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)


class DataSetEndpoint(IdentifiableEndpoint):
    """

    :param object:
    :return:
    """
    def __init__(self, session):
        """

        :param self:
        :param api:
        :return:
        """
        super().__init__()
        self._api = session.dataset
        self._base_type = DataSet

    @decache
    def upload(self, filename, description=None, type_map=None):
        """

        :param filename:
        :param description:
        :param type_map:
        :return:
        """
        if issubclass(type(filename), pd.DataFrame):
            path = os.path.join(tempfile.gettempdir(), gen_id() + ".csv")
            df = filename
            df.to_csv(path, index=False)
            filename = path

        assert(issubclass(type(filename), str))

        if not os.path.exists(filename):
            raise ValueError("No filename given.")

        json = self._api.post(
            file_path=filename,
            description=description if description is not None else '',
            type_map=type_map if type_map is not None else {}
        )
        return DataSet(json)

    @decache
    def remove(self, dataset):
        """

        :param dataset:
        :return:
        """
        self._apply(self._api.delete, dataset, 'delete')

    def show(self):
        """
        Prints the datasetlist
        :return:
        """
        print(self.items)

    @property
    @lru_cache(maxsize=32)
    def columns(self):
        """Get a single dataset at position key"""
        cols = flatten([c.columns for c in self.items])
        return ReadOnlyDict({c.id: c for c in cols})

    @lru_cache(maxsize=32)
    def get(self, key):
        """Get a single dataset at position key"""
        return DataSet(self._api.item(key))

    @property
    @lru_cache(maxsize=32)
    def items(self):
        """Maintains a list of DataSet objects"""
        keys = self._api.keys()
        ds = []
        for k in keys:
            ds.append(DataSet(self._api.item(k)))
        return tuple(ds)


class ModelEndpoint(IdentifiableEndpoint):
    """
    The endpoint for querying the models (lobsters)
    :param object:
    :return:
    """
    def __init__(self, session):
        """

        :param self:
        :param api:
        :return:
        """
        super().__init__()
        self._api = session.model
        self._session = session
        self._base_type = Model

    @decache
    def remove(self, model):
        """
        Remove a model from the server
        :param model: The model or model ID
        :return:
        """
        self._apply(self._api.delete, model, 'delete')

    def show(self):
        """
        Prints the model
        :return:
        """
        print(self.items)

    @lru_cache(maxsize=32)
    def get(self, key):
        """Get a single model at position key"""
        return Model(self._api.item(key), self._session)

    @property
    @lru_cache(maxsize=32)
    def items(self):
        """Maintains a list of Model objects"""
        keys = self._api.keys()
        models = []
        for k in keys:
            blob = self._api.item(k)
            model = Model(blob, self._session)
            models.append(model)
        return tuple(models)


class OntologyEndpoint(IdentifiableEndpoint):
    """
    User facing object used to control the Ontology endpoint.
    Here the user can view the ontology items, upload an
    ontology, update it etc.

    :param IdentifiableEndpoint: An endpoint with a key value
    :return:
    """
    def __init__(self, session):
        """

        :param session:
        :return:
        """
        super().__init__()
        self._api = session.ontology
        self._base_type = Ontology

    @decache
    def upload(self, ontology, description=None, owl_format=None):
        """
        Uploads an ontology to the Serene server.

        :param ontology:
        :param description:
        :param owl_format:
        :return:
        """
        if issubclass(type(ontology), str):
            # must be a direct filename...
            if not os.path.exists(ontology):
                raise ValueError("No filename given.")
            filename = ontology
            output = Ontology(filename)
        elif issubclass(type(ontology), Ontology):
            # this will use the default path and return it if successful...
            filename = ontology.to_turtle()
            output = ontology
        else:
            raise ValueError("Upload requires Ontology type or direct filename")

        json = self._api.post(
            file_path=filename,
            description=description if description is not None else '',
            owl_format=owl_format if owl_format is not None else 'owl'
        )
        return output.update(json)

    @decache
    def update(self, ontology, file=None, description=None, owl_format=None):
        """
        Uploads an ontology to the Serene server.

        :param ontology:
        :param file:
        :param description:
        :param owl_format:
        :return:
        """
        if not issubclass(type(ontology), Ontology):
            raise ValueError("Update requires Ontology type or direct filename")

        if file is not None:
            # this means we are re-doing the whole thing...
            filename = file
            output = Ontology(filename)
        else:
            # this will use the default path and return it if successful...
            filename = ontology.to_turtle()
            output = ontology

        json = self._api.update(
            file_path=filename,
            description=description,
            owl_format=owl_format
        )
        return output.update(json)

    @decache
    def remove(self, ontology):
        """

        :param ontology:
        :return:
        """
        self._apply(self._api.delete, ontology, 'delete')

    def show(self):
        """
        Prints the ontologylist
        :return:
        """
        print(self.items)

    def get(self, key):
        """Get a single ontology at position key"""
        for o in self.items:
            if o.id == key:
                return o
        msg = "Ontology {} does not exist on server".format(key)
        raise Exception(msg)

    @property
    @lru_cache(maxsize=32)
    def items(self):
        """Maintains a list of Ontology objects"""
        keys = self._api.keys()
        ontologies = []
        for k in keys:
            on = Ontology(file=self._api.owl_file(k))
            on.update(self._api.item(k))
            ontologies.append(on)
        return tuple(ontologies)


class SSDEndpoint(IdentifiableEndpoint):
    """

    :param object:
    :return:
    """
    def __init__(self, parent):
        """

        :param self:
        :param api:
        :return:
        """
        super().__init__()
        self._api = parent.session.ssd
        self._session = parent
        self._base_type = SSD

    def compare(self, x, y, ignore_types=True, ignore_columns=False):
        """Compares two SSDs to return something"""
        pass

    @decache
    def upload(self, ssd):
        """
        Uploads an SSD to the Serene server
        :param ssd
        :return:
        """
        assert(issubclass(type(ssd), SSD))

        # test file
        with open('test.json', 'w') as f:
            print("SENDING::::")
            print(ssd.json)
            print("::::")
            f.write(ssd.json)

        response = self._api.post(ssd.json)

        return ssd.update(response, self._session)

    @decache
    def remove(self, ssd):
        """

        :param ssd:
        :return:
        """
        self._apply(self._api.delete, ssd, 'delete')

    def show(self):
        """
        Prints the ssd
        :return:
        """
        print(self.items)

    @lru_cache(maxsize=32)
    def get(self, key):
        """Get a single SSD at position key"""
        return SSD.update(self._api.item(key),
                          self._session.datasets,
                          self._session.ontologies)

    @property
    @lru_cache(maxsize=32)
    def items(self):
        """Maintains a list of SSD objects"""
        keys = self._api.keys()
        ssd = []
        for k in keys:
            blob = self._api.item(k)
            s = SSD.update(blob,
                           self._session.datasets,
                           self._session.ontologies)
            ssd.append(s)
        return tuple(ssd)


class OctopusEndpoint(IdentifiableEndpoint):
    """
    The endpoint object for the Octopus Serene methods
    :param object:
    :return:
    """
    def __init__(self, session):
        """
        Initializes the Octopus endpoint, using a session object
        to populate the SSD and Ontology objects

        :param session: The current live session to communicate with the server
        :return:
        """
        super().__init__()
        self._api = session.octopus
        self._session = session
        self._base_type = Octopus

    @decache
    def upload(self, octopus):
        """
        Uploads an Octopus to the server
        :param octopus: The local Octopus object
        :return:
        """
        assert(issubclass(type(octopus), Octopus))

        for ssd in octopus.ssds:
            if not ssd.stored:
                msg = "SSD is not stored on the server: {}. Use " \
                      "<Serene>.ssd.upload(<SSD>) to update.".format(ssd)
                raise ValueError(msg)

        for ontology in octopus.ontologies:
            if not ontology.stored:
                msg = "Ontology is not stored on the server: {}. Use " \
                      "<Serene>.ontologies.upload(<Ontology>) to update.".format(ontology)
                raise ValueError(msg)

        response = self._api.post(
            ssds=[s.id for s in octopus.ssds],
            name=octopus.name if octopus.name is not None else "unknown",
            description=octopus.description if octopus.description is not None else "",
            feature_config=octopus.feature_config,
            model_type=octopus.model_type if octopus.model_type is not None else "randomForest",
            resampling_strategy=octopus.resampling_strategy,
            num_bags=octopus.num_bags,
            bag_size=octopus.bag_size,
            ontologies=[o.id for o in octopus.ontologies],
            modeling_props=octopus.modeling_props
        )

        return octopus.update(response, self._session)

    @decache
    def remove(self, octopus):
        """
        Removes the Octopus from the server...
        :param octopus: The key or Octopus object to delete from the server...
        :return:
        """
        self._apply(self._api.delete, octopus, 'delete')

    def show(self):
        """
        Prints the Octopus elements on the server.
        :return:
        """
        print(self.items)

    @lru_cache(maxsize=32)
    def get(self, key):
        """Get a single Octopus at position key"""
        for o in self.items:
            if o.id == key:
                return o
        msg = "Octopus {} does not exist on server".format(key)
        raise Exception(msg)

    @property
    @lru_cache(maxsize=32)
    def items(self):
        """Maintains a list of Octopus objects"""
        keys = self._api.keys()
        octopii = []
        for k in keys:
            blob = self._api.item(k)
            o = Octopus().update(blob, self._session)
            octopii.append(o)
        return tuple(octopii)