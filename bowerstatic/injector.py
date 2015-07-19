import webob

CONTENT_TYPES = set(['text/html', 'application/xhtml+xml'])

METHODS = set(['GET', 'POST', 'HEAD'])


class InjectorTween(object):
    def __init__(self, bower, handler):
        self.bower = bower
        self.handler = handler

    def __call__(self, request):
        response = self.handler(request)
        if request.method not in METHODS:
            return response
        if response.content_type is None:  # e.g. 401 reponses
            return response
        if response.content_type.lower() not in CONTENT_TYPES:
            return response
        inclusions = request.environ.get('bowerstatic.inclusions')
        if inclusions is None:
            return response
        body = response.body
        inject_pt = self.bower.inject_point
        head_tag = b'</head>'
        if inject_pt != head_tag and body.find(inject_pt) == -1:
            inject_pt = head_tag

        response.body = b''
        rendered_inclusions = (inclusions.render() + inject_pt).encode('utf-8')
        body = body.replace(inject_pt, rendered_inclusions)
        response.write(body)
        return response


class Injector(object):
    def __init__(self, bower, wsgi):
        def handler(request):
            return request.get_response(wsgi)
        self.tween = InjectorTween(bower, handler)

    @webob.dec.wsgify
    def __call__(self, request):
        return self.tween(request)
