# 能力策略常见问题

## 为什么调试时 http_call 没有真实发请求？

多为命中 suppress 后的占位返回值。调试入口固定为调试模式，integration 等副作用类内置函数默认会被抑制。联调沙箱请在 **本次附加策略** 或节点 **节点能力策略** 中配置 allow / redirect。

## REDIRECT 会自动改 URL 吗？

不会。REDIRECT 只是把参数传给 builtin（通过 `redirect_params`）。是否重定向、怎么重定向由 builtin 具体实现决定。

## 能在调试入口切到 production 吗？

不能。临时调试入口服务端锁死 DEBUG，避免误触发真实生产副作用。生产行为请走部署路径。

## 相关文档

- [调用为何被抑制](why-calls-are-suppressed.md)
