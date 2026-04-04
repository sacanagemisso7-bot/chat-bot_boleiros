from db import create_cliente_placeholder, update_cliente_nome


class OnboardingService:
    @staticmethod
    def start(telefone: str):
        return create_cliente_placeholder(telefone)

    @staticmethod
    def finalize(cliente_id: int, nome: str) -> None:
        update_cliente_nome(cliente_id, nome)
