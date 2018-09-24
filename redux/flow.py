'''
Flow 是一种基于AnyMessage和CombineMessage的组合流程
一个具体系统无法避免多层嵌套的异步流程，中间可能需要多次和其他ReducerNode完成Action传输，之后可以完成整体的功能

我们首先假设，在一个复杂流程中，正确的Action流只有一个，其他的等待结果，都是不正确的，基本上会出现类似JavaScript的异步处理风格
do(sth)
.then(sth)
.then(sth)
...
.error(e)
'''