"""Small Tools & setup integration; jobs remain in the established worker runner."""
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path

from downloads import DEFAULT_REPLAYS
from jobs import STATE
from skybox_sync import build_command
from sources import classify_link, SourceError


def catalog_players(catalog):
    """Use the report module's stable identities, not a second player store."""
    if not isinstance(catalog,dict) or catalog.get('version')!=3:return {}
    return {str(t['name'])+' · '+t['steamid']:t['steamid'] for t in catalog.get('targets',[])
            if t.get('mode')=='player' and isinstance(t.get('steamid'),str)
            and len(t['steamid'])==17 and t['steamid'].isdigit()}


class SkyboxTools:
    def skybox_card(self):
        card=self.card('SKYBOX DEMOS')
        self.text(card,'FACEIT profile link',9).pack(anchor='w')
        profile=self.var('skybox_profile','')
        # Older picker labels are not profile links. Never guess an account from a name.
        try:
            link=classify_link(profile.get())
            valid=link['source']=='faceit' and link['kind']=='player'
        except SourceError:valid=False
        if not valid:
            candidate=self.settings.get('download_link','')
            try:
                link=classify_link(candidate)
                candidate=candidate if link['source']=='faceit' and link['kind']=='player' else ''
            except SourceError:candidate=''
            profile.set(candidate)
        ttk.Entry(card,textvariable=profile).pack(fill='x',pady=(5,12))
        row=tk.Frame(card,bg=card.cget('bg'));row.pack(fill='x')
        self.text(row,'Number of demos',9).pack(side='left',padx=(0,10))
        ttk.Spinbox(row,from_=1,to=100,width=6,textvariable=self.var('skybox_count','10')).pack(side='left',padx=(0,16))
        self.action(row,'Upload to Skybox',self.run_skybox)

    def run_skybox(self,inventory=False):
        try:
            value=self.var('skybox_profile').get().strip()
            command=build_command(profile=value,count=self.var('skybox_count','10').get(),
                root=str(DEFAULT_REPLAYS),inventory=inventory,
                method='automatic',
                watch=self.var('browser_downloads',str(Path.home()/'Downloads')).get())
        except ValueError as exc:
            messagebox.showerror('Skybox setup needed',str(exc),parent=self);return
        if not inventory:self.save_settings()
        self.launch_job('Inventory Skybox' if inventory else 'Upload newest missing FACEIT demos to Skybox',command,output=str(STATE/'skybox'))
