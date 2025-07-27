"""Retry utility functions with exponential backoff for network operations"""

import asyncio
import logging
import inspect
import time
from functools import wraps
from typing import Callable, Any, Tuple, Union, Type, Optional
import aiohttp
from .config import config


def _retry_logic_generator(func_name: str, max_retries: int, base_delay: float, 
                         max_delay: float, backoff_factor: float, retry_exceptions: Tuple[Type[Exception], ...]):
    """
    Generator that yields retry attempts and handles shared retry logic.
    
    Yields:
        tuple: (attempt_number, delay_before_retry_or_None)
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            yield attempt, None  # Signal to try the function
            return  # Success - exit the generator
        except retry_exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                logging.error(
                    f"Function {func_name} failed after {max_retries} retries. "
                    f"Last error: {str(e)}"
                )
                raise e
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            
            logging.warning(
                f"Function {func_name} attempt {attempt + 1} failed: {str(e)}. "
                f"Retrying in {delay:.2f} seconds..."
            )
            
            yield attempt, delay  # Signal to sleep before retry
        except Exception as e:
            # Re-raise exceptions that are not in the retry list
            logging.error(f"Function {func_name} failed with non-retryable error: {str(e)}")
            raise e
    
    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


def retry_with_exponential_backoff(
    max_retries: int = config.max_retries,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: Optional[Tuple[Type[Exception], ...]] = None
):
    
    def decorator(func: Callable) -> Callable:
        is_async = inspect.iscoroutinefunction(func)
        
        # Auto-detect exceptions based on function type if not provided
        if exceptions is None:
            if is_async:
                retry_exceptions = (
                    aiohttp.ClientError,
                    aiohttp.ServerTimeoutError,
                    asyncio.TimeoutError,
                    ConnectionError,
                )
            else:
                retry_exceptions = (
                    ConnectionError,
                    TimeoutError,
                )
        else:
            retry_exceptions = exceptions
        
        if is_async:
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                retry_gen = _retry_logic_generator(
                    func.__name__, max_retries, base_delay, max_delay, 
                    backoff_factor, retry_exceptions
                )
                
                for _, delay in retry_gen:
                    if delay is None:
                        # Attempt to call the function
                        try:
                            result = await func(*args, **kwargs)
                            retry_gen.close()  # Success - close generator
                            return result
                        except Exception as e:
                            retry_gen.throw(type(e), e, e.__traceback__)
                    else:
                        # Sleep before retry
                        await asyncio.sleep(delay)
            
            return async_wrapper
        
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                retry_gen = _retry_logic_generator(
                    func.__name__, max_retries, base_delay, max_delay, 
                    backoff_factor, retry_exceptions
                )
                
                for _, delay in retry_gen:
                    if delay is None:
                        # Attempt to call the function
                        try:
                            result = func(*args, **kwargs)
                            retry_gen.close()  # Success - close generator
                            return result
                        except Exception as e:
                            retry_gen.throw(type(e), e, e.__traceback__)
                    else:
                        # Sleep before retry
                        time.sleep(delay)
            
            return sync_wrapper
    
    return decorator


# Backward compatibility aliases
sync_retry_with_exponential_backoff = retry_with_exponential_backoff