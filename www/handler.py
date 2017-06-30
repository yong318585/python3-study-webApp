from coreWeb import get, post
from aiohttp import web

import re, time, json, logging, hashlib, base64, asyncio
import markdown2
from apiError import APIValueError, APIResourceNotFoundError,APIError,APIPermissionError
from model import User, Comment, Blog, next_id
from config import configs
COOKIE_NAME = 'awesession'
MAX_AGE = 86400
_COOKIE_KEY = configs.session.secret

# @get('/')
# async def index(request):
#     users = await User.findAll()
#     return {
#         '__template__':'test.html',
#         'users':users
#     }



@get('/')
def index(request):
    summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
    blogs = [
        Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
        Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
        Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
    ]
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }

@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }
@get('/api/users')
async def api_get_users():
    users = await User.findAll(orderBy='created_at desc')
    for u in users:
        u.passwd='******'
    return dict(users=users)

@get('/signin')
def signin():
    return{
        '__template__':'signin.html'
    }

@get('/signout')
def sigout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME,'-deleted-',max_age=0,httponly=True)
    logging.info('user sigout')
    return r

_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')
@post('/api/users')
async def api_register_user(*,email,name,passwd):
    if not name or not name.strip():
        raise  APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise  APIValueError('email')
    if not passwd or not  _RE_SHA1.match(passwd):
        raise APIValueError('password')
    users = await  User.findAll('email=?',[email])

    if len(users) > 0:
        raise APIError('register:failed','email','email is already in use')
    uid = next_id()
    sha1_passwd = '%s:%s'%(uid,passwd)

    user = User(id = uid,name=name.strip(),email=email,passwd = hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),admin=True,image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await  user.save()
    r = web.Response()
    r.set_cookie(COOKIE_NAME,user2cookie(user,MAX_AGE),max_age=MAX_AGE,httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    # 想输出真正的中文需要指定ensure_ascii = False
    r.body = json.dumps(user,ensure_ascii=False).encode('utf-8')
    return r



@post('/api/authenticate')
async def authenticate(*,email,passwd):
    logging.info('authenticate .....begin...')
    if not email:
        raise APIValueError('email','Invaid email')
    if not passwd:
        raise APIValueError('passwd','Invail passwd.')

    users = await User.findAll('email=?',[email])
    if len(users) == 0:
        raise APIValueError('email','email not exist')
    user = users[0]
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd != sha1.hexdigest():
        raise  APIValueError('passwd','Invalid password')

    r = web.Response()
    r.set_cookie(COOKIE_NAME,user2cookie(user,MAX_AGE),max_age=MAX_AGE,httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user,ensure_ascii=False).encode('utf-8')
    logging.info('authenticate .....end...')
    return r

def user2cookie(user,max_age):
    expires = str(int(time.time()+max_age))
    s = '%s-%s-%s-%s'%(user.id,user.passwd,expires,_COOKIE_KEY)
    L = [user.id,expires,hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)

def cookie2user(cookie_str):
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-')
        if len(L)!=3:
            return None
        uid,expires,sha1 = L
        if int(expires) < time.time():
            return  None
        user = yield  from  User.find(uid)
        if user is None:
            return None
        s = '%s-%s-%s-%s'%(uid,user.passwd,expires,_COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '****'
        return user
    except Exception as e:
        logging.exception(e)
        return  None
def text2html(text):
    lines = map(lambda s:'<p>%s</p>'%s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'),filter(lambda  s:s.strip() !='',text.split('\n')))
    return ''.join(lines)

@get('/blog/{id}')
def get_blog(id):
    blog = yield from Blog.find(id)
    comments = yield from Comment.findAll('blog_id?',[id],orderBy='created_at desc')
    for c  in comments:
        c.html_content = text2html(c.content)
    blog.html_content=markdown2.markdown(blog.content)
    return {
        '__template__':'blog.html',
        'blog':blog,
        'comments':comments
    }

@get('/manage/blogs/create')
def manage_create_blog():
    return {
        '__template__':'manage_blog_edit.html',
        'id':'',
        'action':'/api/blogs'
    }

@get('/api/blogs/{id}')
def api_get_blog(*,id):
    blog = yield from  Blog.find(id)
    return blog

def check_admin(request):
    logging.info('check_admin>>>%s'%request.__user__)
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError

@post('/api/blogs')
def api_create_blog(request,*,name,summary,content):
    check_admin(request)
    if not name or not name.strip():
        raise  APIValueError('name','name cannot be null')
    if not summary or not summary.strip():
        raise  APIValueError('summary','summary cannot be null')
    if not content or not content.strip():
        raise  APIValueError('content','content cannot be null')
    blog = Blog(user_id = request.__user__.id,user_name=request.__user__.name,user_image=request.__user__.image,name=name.strip(),summary=summary.strip(),content=content.strip())
    yield from blog.save()
    return blog
