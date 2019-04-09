import logging
import sentry_sdk


class SentryMiddleware(object):
    def on_error(self, error):
        logging.exception('GraphQL exception', exc_info=error)
        sentry_sdk.capture_exception(error)
        raise error

    def resolve(self, next, *args, **kwargs):
        return next(*args, **kwargs).catch(self.on_error)
