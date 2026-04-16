# src/app_auth/exceptions.py
from fastapi import status, HTTPException

UserAlreadyExistsException = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь уже существует")
UserNotFoundException = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")
UserIdNotFoundException = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Отсутствует идентификатор пользователя")
IncorrectEmailOrPasswordException = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неверная почта или пароль")
TokenExpiredException = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен истек")
InvalidTokenFormatException = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный формат токена")
TokenNoFound = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Токен отсутствует в заголовке")
NoJwtException = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Токен не валидный")
NoUserIdException = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Не найден ID пользователя")
ForbiddenException = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")