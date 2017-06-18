import asyncio
import functools
import inspect
from aiohttp import web
from  urllib import  parse
from apiError import APIError
import logging;

logging.basicConfig(level=logging.INFO)
import os


def request(path, method):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = method
        wrapper.__route__ = path
        return wrapper

    return decorator


get = functools.partial(request, method='GET')
post = functools.partial(request, method='POST')
put = functools.partial(request, method='PUT')
delete = functools.partial(request, method='DELETE')


# inspect.Parameter对象的default属性：如果这个参数有默认值，即返回这个默认值，如果没有，返回一个inspect._empty类
def get_required_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name,param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default==inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


# 有默认参数
def get_named_kw_args(fn):
    args=[]
    params = inspect.signature(fn).parameters
    for name,param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)

def has_name_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name,param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            logging.info("has_name_kw_arg is true")
            return True
        else:
            logging.info("has_name_kw_arg is false")
            return False

def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name,param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            logging.info("has var_kw_arg")
            return True
        else:
            logging.info("has no var_kw_arg")
            return False

def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name,param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and  param.kind != inspect.Parameter.VAR_KEYWORD):
            raise  ValueError('request parameter must b the last name parameter in function:%s%s'%(fn.__name__,str(sig)))
    logging.info('has_request_arg>>>>>%s'%found)
    return  found


class RequestHandler(object):
    def __init__(self,app, func):
        self._app = app
        self._func = asyncio.coroutine(func)
        self._has_request_arg=has_request_arg(func)
        self._has_var_kw_args = has_var_kw_arg(func)
        self._has_named_kw_args = has_name_kw_arg(func)
        self._named_kw_args = get_named_kw_args(func)
        self._required_kw_arg = get_required_kw_args(func)

    async def __call__(self, request, kw=None):
        logging.info('coreweb.call........')
        if self._has_request_arg or self._has_named_kw_args or self._required_kw_arg:
            logging.info('request.method>>>%s'%request.method)
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest('mssiing content-type')
                ct = request().content_type.lower()
                if ct.startwith('application/json'):
                    params = await request.json()
                    if not isinstance(params,dict):
                        return  web.HTTPBadRequest('json body must be object')
                    kw = params
                elif ct.startwith('application/x-wwww-form-urlencoded') or ct.startwith('multipart/form-data'):
                    params = await  request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest('unsupported Content-Type:%s'%request.content_type)
            if request.method=='GET':
                qs = request.query_string
                logging.info('qs>>>%s'%qs)
                if qs:
                    kw = dict()
                    for k,v in parse.parse_qs(qs,True).items():
                        kw[k]=v[0]
        if kw is None:
            # logging.info('request.matc_info>>>%s'%request.match_info)
            kw=dict(**request.match_info)
        else:
            if not self._has_var_kw_args and self._has_named_kw_args:
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            for k,v in request.match_info.items():
                if k in kw:
                    logging.warning('duplicate arg name in named arg and kw ags:%s'%k)
                kw[k] = v

        if self._has_request_arg:
            kw['request'] = request
        if self._required_kw_arg:
            for name in self._has_request_arg:
                if not name in kw:
                    return web.HTTPBadRequest('Missing argument:%s'%name)
        logging.info('call with args:%s'%str(kw))
        try:
            r = await  self._func(**kw)
            return r
        except APIError as e:
            return  dict(error=e.error,data=e.data,message = e.message)



# 注册一个URL处理函数
def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.' % str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info(
        'add route %s %s => %s(%s)' % (method, path, fn.__name__, ', '.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app,fn))


def add_routes(app, module_name):
    # 返回字符串最后一次出现的位置，如果没有匹配项则返回-1
    n = module_name.rfind('.')
    logging.info('module_name>>>%s>>>%s' % (module_name, n))
    if n == -1:
        mod = __import__(module_name, globals(), locals())
    else:
        name = module_name[n + 1:]
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):
        # 如果是以'_'开头的，一律pass，我们定义的处理方法不是以'_'开头的
        if attr.startswith('_'):
            continue
        fn = getattr(mod, attr)
        if callable(fn):
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)


def add_static(app):
    logging.info('os.path.abspath(__file__)>>>%s' % os.path.split(os.path.abspath(__file__))[0])
    path = os.path.join(os.path.split(os.path.abspath(__file__))[0], 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))



























