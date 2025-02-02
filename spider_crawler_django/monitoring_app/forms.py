from django import forms


class DominioForm(forms.Form):
    dominio = forms.CharField(label='Dominio (Ej. ubi.com)', max_length=200)