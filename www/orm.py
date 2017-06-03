
import asyncio
import logging;logging.basicConfig(level = logging.INFO)
# http://blog.csdn.net/haskei/article/details/57075381
# https://github.com/wl356485255/pythonORM/blob/master/orm.py
@asyncio.coroutine
def create_pool(loop,**kw):
	logging.info('create database connection pool...')
	global __pool
	__pool = yield from  aiomysql.create_pool(
		host = kw.get('host','localhost'),
		port = kw.get('port',3306),
		user= kw['user'],
		password = kw['password'],
		db = kw['db'],
		charset = kw.get('charset','utf8'),
		autocommit = kw.get('autocommit',True),
		maxsize = kw.get('maxsize',10),
		minsize = kw.get('minsize',1),
		loop = loop
		)

@asyncio.coroutine
def select(sql,args,size=None):
	log(sql,args)
	global __pool
	with(yield from __pool) as conn:
		cur = yield from conn.cursor(aiomysql.DictCurson)
		yield from cur.execute(sql.replace('?','%s'),args or ())	
		if size:
			rs = yield from cur.fetchmany(size)
		else:
			rs = yield from cur.fetchall()
		yield from cur.close()
		logging.info('rows  returned:%s'%len(rs))
		return rs

@asyncio.coroutine
def execute(sql,args):
	log(sql)
	with (yield from __pool) as conn:
		try:
			cur = yield from conn.cursor()
			yield from cur.execute(sql.replace('?','%s'),args)
			affected = cur.rowcount
			yield from cur.close()
		except BaseException as e:
			raise e		
		return affected		

class  Field(object):
	def __init__(self,name,column_type,primary_key,default):
		self.name = name
		self.column_type = column_type
		self.primary_key = primary_key
		self.default = default
	# 当打印(数据库)表时，输出(数据库)表的信息:类名，字段类型和名字
	def __str__(self):
		return ('<%s,%s,%s>'%(self.__class__.__name__,self.column_type,self.name))

class StringField(Field):
		"""docstring for StringField"""
		def __init__(self, name = None,primary_key=False,default=None,column_type='varchar(100)'):
			super().__init__(name,column_type,primary_key,default)

class BoolearField(Field):
	def __init__(self,name=None,default =None):
		super().__init__(name,'boolean',False,default)

class IntegerField(Field):
	def __init__(self,name=None,primary_key=False,default=0):
		super().__init__(name,'bigint',primary_key,default)
		
class FloatField(Field):
	def __init__(self,name=None,primary_key=False,default=0.0):
		super().__init__(name,'real',primary_key,default)

class TextField(Field):
	def __init__(self,name=None,default=None):
		super().__init__(name,'Text',False,default)
	


						
def create_args_string(num):
	l = []
	for n in range(num):
		l.append('?')
	return ','.join(l)			
								
			
								

class ModelMetaclass(type):
	# __new__控制__init__的执行，所以在其执行之前
    # cls:代表要__init__的类，此参数在实例化时由Python解释器自动提供(例如下文的User和Model)
    # bases：代表继承父类的集合
    # attrs：类的方法集合
	def __new__(cls,name,bases,attrs):
		if name == 'Model':
			return type.__new__(cls,name,bases,attrs)
		tableName =  attrs.get('__table__',None) or name	
		logging.info('found model:%s(table:%s)'%(name,tableName))
		mappings = dict()
		fields = []
		primaryKey = None
		for  k,v in attrs.items():
			if isinstance(v,Field):
				logging.info('found mapping:%s--->%s'%(k,v))
				mappings[k]=v

				if v.primary_key:
					if primaryKey:
						raise BaseException('Dupicate primary key for  field:%s'%k)
					primaryKey=k
				else:
					fields.append(k)
		if not primaryKey:
			raise BaseException('primaryKey is not found')
		for k in mappings.keys():
			attrs.pop(k)
		escaped_fields=list(map(lambda f:'`%s`'%f,fields))	
		logging.info('escaped_fields>>>%s'%escaped_fields)
		attrs['__mappings__']=mappings
		attrs['__table__']=tableName
		attrs['__primary_key__']=primaryKey
		attrs['__fields__']= fields
		 # 反引号和repr()函数功能一致
		attrs['__select__']='select `%s`,%s  from `%s`'%(primaryKey,','.join(escaped_fields),tableName)
		attrs['__insert__']='insert into `%s`(%s,`%s`) values(%s)'%(tableName,','.join(escaped_fields),primaryKey,create_args_string(len(escaped_fields)+1))
		attrs['__update__']='update `%s` set `%s` where `%s`=?'%(tableName,', '.join(map(lambda f:'`%s`=?'%(mappings.get(f).name or f),fields)),primaryKey)	
		attrs['__delete__']='delete from `%s` where `%s`=?'%(tableName,primaryKey)
		return type.__new__(cls,name,bases,attrs)					

		


class Model(dict,metaclass=ModelMetaclass):
	def __init__(self,**kw):
		super(Model,self).__init__(**kw)

	def __getattr__(self,key):
		try:
			return self[key]
		except KeyError:
			raise  AttributeError(r"'Model' object has no attribute '%s'" % key) 	
	def __setattr__(self,key,value):
		self[key]=value

	def getValue(self,key):
		return getattr(self,key,None)
	def getValueOrDefault(self,key):
		value = getattr(self,key,None)
		if value  is None:
			field = self.__mappings__[key]
			if  field.default is not None:
				value = field.default()  if callable(field.default) else field.default
				logging.debug('using default value for %s:%s'%(key,str(value)))
				setattr(self,key,value)
		return value		






# 类方法的第一个参数是cls,而实例方法的第一个参数是self
	@classmethod
	async def findAll(cls,where = None,args=None,**kw):
		sql =[cls.__select__]
		if where:
			sql.append('where')
			sql.append(where)
		if args is None:
			args = []

		orderBy = kw.get('orderBy',None)
		if orderBy:
			sql.append('order by')
			sql.append(orderBy)
		limit = kw.get('limit',None)
		if  limit is not None:
			sql.append('limit')
			if isinstance(limit,int):
				sql.append('?')
				args.append(limit)
			elif isinstance(limit,tuple) and len(limit)==2:
				sql.append('?','?')
				args.extend(limit)				
			else:
				raise ValueError('Invalid limit value:%s'%str(limit))
		rs = await select(' '.join(sql),args)
		return [cls(**r) for  r in rs]			

	@classmethod
	async def findNumber(cls,selectedField,where=None,args=None):
		sql = ['select %s _num_ from `%s`'%(selectedField,cls.__table__)]
		if where:
			sql.append('where')
			sql.append(where)
			rs = await select(' '.join(sql),args,1)
			if len(rs)==0:
				return None
			return rs[0]['_num_']



	@classmethod
	async def find(cls,pk):
		rs  = await select('%s where `%s`=?'%(cls.__select__,cls.__primary_key__),[pk],1)
		if len(rs) == 0:
			return None
		return cls(**rs[0])	



	async def save(self):
		args = list(map(self.getValueOrDefault,self.__fields__))
		args.append(self.getValueOrDefault(self.__primary_key__))
		rows = await execute(self.__insert__,args)
		if row !=1:
			logging.warning('failed to insert  record:affected rows:%s'%rows)

	async def update(self):
		args = list(map(self.getValue,self.__fields__))
		args.append(self.getValue(self.__primary_key__))
		rows = await execute(self.__update__,args)		
		if  rows != 1:
			logging.warning('failed to update by primary_key:affected rows:%s'%rows)

	async def remove(self):
		args = [self.getValue(self.__primary_key__)]
		rows = await execute(self.__delete__,args)
		if rows != 1:
			logging.warning('failed to remove by primary key :affected rows:%s'%rows)		

			



if __name__ == '__main__':
     
    class User(Model):
        # 定义类的属性到列的映射：
        id = IntegerField('id',primary_key=True)
        name = StringField('username')
        email = StringField('email')
        password = StringField('password')
 
    # 创建一个实例：
    u = User(id=12345, name='peic', email='peic@python.org', password='password')
    print(u)
    # # 保存到数据库：
    u.save()
    # print(u)
    # u.insert()
    print(u)
    
 
    print(u['id'])



























