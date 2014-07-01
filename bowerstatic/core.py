import os
import json
from .publisher import Publisher
from .injector import Injector
from .includer import Includer


class Error(Exception):
    pass


class Bower(object):
    """Contains a bunch of bower_components directories.
    """
    def __init__(self, publisher_signature='bowerstatic'):
        self.publisher_signature = publisher_signature
        self._components_directories = {}
        self._local = {}

    def components(self, name, path):
        if name in self._components_directories:
            raise Error("Duplicate name for components directory: %s" % name)
        result = ComponentsDirectory(self, name, path)
        self._components_directories[name] = result
        return result

    def local_components(self, name, components_directory):
        if name in self._local:
            raise Error("Duplicate name for local components: %s" % name)
        result = LocalComponents(self, name, components_directory)
        self._local[name] = result
        return result

    def wrap(self, wsgi):
        return self.publisher(self.injector(wsgi))

    def publisher(self, wsgi):
        return Publisher(self, wsgi)

    def injector(self, wsgi):
        return Injector(self, wsgi)

    def get_filename(self, bower_components_name,
                     component_name, component_version, file_path):
        components_directory = self._components_directories.get(
            bower_components_name)
        if components_directory is None:
            return None
        return components_directory.get_filename(component_name,
                                                 component_version,
                                                 file_path)


class ComponentCollection(object):
    def __init__(self, bower, name):
        self.bower = bower
        self.name = name
        self._resources = {}

    def includer(self, environ):
        return Includer(self.bower, self, environ)

    def resource(self, path, dependencies=None):
        dependencies = dependencies or []
        resource = self._resources.get(path)
        if resource is not None:
            return resource
        result = Resource(self.bower, self, path, dependencies)
        self._resources[path] = result
        return result

class ComponentsDirectory(object):
    def __init__(self, bower, name, path):
        self.bower = bower
        self.name = name
        self.path = path
        self._components = load_components(path)
        self._resources = {}
        for component in self._components.values():
            component.create_main_resource(self)

    def includer(self, environ):
        return Includer(self.bower, self, environ)

    def resource(self, path, dependencies=None):
        dependencies = dependencies or []
        resource = self._resources.get(path)
        if resource is not None:
            return resource
        result = Resource(self.bower, self, path, dependencies)
        self._resources[path] = result
        return result

    def get_resource(self, path):
        return self._resources.get(path)

    def path_to_resource(self, path_or_resource):
        if isinstance(path_or_resource, basestring):
            return self.resource(path_or_resource)
        else:
            resource = path_or_resource
            assert resource.components_directory is self
        return resource

    def get_component(self, component_name):
        return self._components.get(component_name)

    def get_filename(self, component_name, component_version, file_path):
        component = self._components.get(component_name)
        if component is None:
            return None
        return component.get_filename(component_version, file_path)


class LocalComponent(object):
    def __init__(self, path, version):
        self.path = path
        self.version = version
        self.component = load_component(path, 'bower.json')
        self.name = self.component.name

def load_components(path):
    result = {}
    for component_path in os.listdir(path):
        fullpath = os.path.join(path, component_path)
        if not os.path.isdir(fullpath):
            continue
        component = load_component(fullpath, '.bower.json')
        result[component.name] = component
    return result


def load_component(path, bower_filename):
    bower_json_filename = os.path.join(path, bower_filename)
    with open(bower_json_filename, 'rb') as f:
        data = json.load(f)
    if isinstance(data['main'], list):
        main = data['main'][0]
    else:
        main = data['main']
    dependencies = data.get('dependencies')
    if dependencies is None:
        dependencies = {}
    return Component(path,
                     data['name'],
                     data['version'],
                     main,
                     dependencies)


class Component(object):
    def __init__(self, path, name, version, main, dependencies):
        self.path = path
        self.name = name
        self.version = version
        self.main = main
        self.dependencies = dependencies

    def create_main_resource(self, components_directory):
        # if the resource was already created, return it
        resource = components_directory.get_resource(self.name)
        if resource is not None:
            return resource
        # create a main resource for all dependencies
        dependencies = []
        for component_name in self.dependencies.keys():
            component = components_directory.get_component(component_name)
            dependencies.append(
                component.create_main_resource(components_directory))
        # depend on those main resources in this resource
        return components_directory.resource(
            self.name, dependencies=dependencies)

    def get_filename(self, version, file_path):
        if version != self.version:
            return None
        filename = os.path.abspath(os.path.join(self.path, file_path))
        # sanity check to prevent file_path to escape from path
        if not filename.startswith(self.path):
            return None
        return filename


class Resource(object):
    def __init__(self, bower, components_directory, path, dependencies):
        self.bower = bower
        self.components_directory = components_directory
        self.path = path
        self.dependencies = [
            components_directory.path_to_resource(dependency) for
            dependency in dependencies]

        parts = path.split('/', 1)
        if len(parts) == 2:
            component_name, file_path = parts
        else:
            component_name = parts[0]
            file_path = None
        self.component = self.components_directory.get_component(component_name)
        if self.component is None:
            raise Error(
                "Component %s not known in components directory %s (%s)" % (
                    component_name, components_directory.name,
                    components_directory.path))
        if file_path is None:
            file_path = self.component.main
        self.file_path = file_path
        dummy, self.ext = os.path.splitext(file_path)

    def url(self):
        parts = [
            self.bower.publisher_signature,
            self.components_directory.name,
            self.component.name,
            self.component.version,
            self.file_path]
        return '/' + '/'.join(parts)
