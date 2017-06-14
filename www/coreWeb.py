import asyncio
import functools
import inspect
from aiohttp import web

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


class RequestHandler(object):
    def __init__(self, func):
        self._func = asyncio.coroutine(func)

    async def __call__(self, request):
        required_args = inspect.signature(self._func).parameters
        logging.info('required args:%s' % required_args)
        # 获取从GET或POST传进来的参数值，如果函数参数表有这参数名就加入
        kw = {arg: value for arg, value in request.__data__.items() if arg in required_args}
        # 获取match_info的参数值，例如@get('/blog/{id}')之类的参数值
        kw.update(request.match_info)

        if 'request' in required_args:
            kw['request'] = request

        for key, arg in required_args.items:
            if key == 'request' and arg.kind in (arg.VAR_POSITIONAL, arg.VAR_KEYWORD):
                return web.HTTPBadRequest(text='request parameter cannot b the var  argument')
            # 如果参数类型不是变长列表和变长字典，变长参数是可缺省的
            if arg.kind not in (arg.VAR_POSITIONAL, arg.VAR_KEYWORD):
                # 如果还是没有默认值，而且还没有传值的话就报错
                if arg.default == arg.empty and arg.name not in kw:
                    return web.HTTPBadRequest(text='missing argument:%s' % arg.name)
        logging.info('call  with args:%s' % kw)
        try:
            return await self._func(**kw)
        except Exception as e:
            raise e


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
    app.router.add_route(method, path, RequestHandler(fn))


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



























