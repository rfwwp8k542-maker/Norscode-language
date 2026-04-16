use crate::error::RuntimeError;
use crate::gui::GuiState;
use crate::stdio::Io;
use crate::value::Value;
use crate::vm::Vm;

pub(crate) fn handle_gui_builtin<I: Io>(
    vm: &mut Vm<I>,
    name: &str,
    args: &[Value],
) -> Result<Option<Value>, RuntimeError> {
    match name {
        "gui_vindu" => {
            let title = args.first().map(format_value).unwrap_or_default();
            let object_id = vm.gui.create_window(&title);
            Ok(Some(Value::Int(object_id as i64)))
        }
        "gui_panel" => create_widget(vm, "panel", args),
        "gui_rad" => create_widget(vm, "row", args),
        "gui_tekst" => create_widget(vm, "text", args),
        "gui_tekstboks" => create_widget(vm, "text_field", args),
        "gui_editor" => create_widget(vm, "editor", args),
        "gui_liste" => create_widget(vm, "list", args),
        "gui_knapp" => create_widget(vm, "button", args),
        "gui_etikett" => create_widget(vm, "label", args),
        "gui_tekstfelt" => create_widget(vm, "text_field", args),
        "gui_editor_hopp_til" => {
            let object_id = read_int(args.first(), "gui_editor_hopp_til forventer editor-id")?;
            let line = read_int(args.get(1), "gui_editor_hopp_til forventer linjenummer")?;
            Ok(Some(Value::Int(vm.gui.editor_jump_to_line(object_id as usize, line)? as i64)))
        }
        "gui_editor_cursor" => {
            let object_id = read_int(args.first(), "gui_editor_cursor forventer editor-id")?;
            Ok(Some(vm.gui.editor_cursor(object_id as usize)?))
        }
        "gui_editor_erstatt_fra_til" => {
            let object_id = read_int(args.first(), "gui_editor_erstatt_fra_til forventer editor-id")?;
            let start_line = read_int(args.get(1), "gui_editor_erstatt_fra_til mangler start_linje")?;
            let start_col = read_int(args.get(2), "gui_editor_erstatt_fra_til mangler start_kol")?;
            let end_line = read_int(args.get(3), "gui_editor_erstatt_fra_til mangler slutt_linje")?;
            let end_col = read_int(args.get(4), "gui_editor_erstatt_fra_til mangler slutt_kol")?;
            let replacement = args.get(5).map(format_value).unwrap_or_default();
            let callback = vm.gui.editor_replace_range(
                object_id as usize,
                start_line,
                start_col,
                end_line,
                end_col,
                &replacement,
            )?;
            if let Some(callback) = callback {
                invoke_callback(vm, &callback, object_id as usize)?;
            }
            Ok(Some(Value::Int(object_id)))
        }
        "gui_liste_legg_til" => {
            let object_id = read_int(args.first(), "gui_liste_legg_til forventer liste-id")?;
            let text = args.get(1).map(format_value).unwrap_or_default();
            Ok(Some(Value::Int(vm.gui.list_add(object_id as usize, &text)? as i64)))
        }
        "gui_liste_tom" => {
            let object_id = read_int(args.first(), "gui_liste_tom forventer liste-id")?;
            Ok(Some(Value::Int(vm.gui.list_clear(object_id as usize)? as i64)))
        }
        "gui_liste_antall" => {
            let object_id = read_int(args.first(), "gui_liste_antall forventer liste-id")?;
            Ok(Some(Value::Int(vm.gui.list_len(object_id as usize)? as i64)))
        }
        "gui_liste_filer_tre" => {
            let root = args.first().map(format_value).unwrap_or_else(|| ".".to_string());
            let result = GuiState::list_files_tree(&root);
            Ok(Some(Value::list(result.into_iter().map(Value::Text).collect())))
        }
        "gui_liste_hent" => {
            let object_id = read_int(args.first(), "gui_liste_hent forventer liste-id")?;
            let index = read_int(args.get(1), "gui_liste_hent forventer indeks")?;
            Ok(Some(Value::Text(vm.gui.list_get(object_id as usize, index)?)))
        }
        "gui_liste_fjern" => {
            let object_id = read_int(args.first(), "gui_liste_fjern forventer liste-id")?;
            let index = read_int(args.get(1), "gui_liste_fjern forventer indeks")?;
            let callback = vm.gui.list_remove(object_id as usize, index)?;
            if let Some(callback) = callback {
                invoke_callback(vm, &callback, object_id as usize)?;
            }
            Ok(Some(Value::Int(object_id)))
        }
        "gui_liste_valgt" => {
            let object_id = read_int(args.first(), "gui_liste_valgt forventer liste-id")?;
            Ok(Some(Value::Text(vm.gui.list_selected_text(object_id as usize)?)))
        }
        "gui_liste_velg" => {
            let object_id = read_int(args.first(), "gui_liste_velg forventer liste-id")?;
            let index = read_int(args.get(1), "gui_liste_velg forventer indeks")?;
            let callback = vm.gui.list_select(object_id as usize, index)?;
            if let Some(callback) = callback {
                invoke_callback(vm, &callback, object_id as usize)?;
            }
            Ok(Some(Value::Int(object_id)))
        }
        "gui_på_klikk" => {
            let object_id = read_int(args.first(), "gui_på_klikk forventer widget-id")?;
            let callback = args.get(1).map(format_value).unwrap_or_default();
            Ok(Some(Value::Int(vm.gui.register_click(object_id as usize, &callback)? as i64)))
        }
        "gui_på_endring" => {
            let object_id = read_int(args.first(), "gui_på_endring forventer widget-id")?;
            let callback = args.get(1).map(format_value).unwrap_or_default();
            Ok(Some(Value::Int(vm.gui.register_change(object_id as usize, &callback)? as i64)))
        }
        "gui_på_tast" => {
            let object_id = read_int(args.first(), "gui_på_tast forventer widget-id")?;
            let key = args.get(1).map(format_value).unwrap_or_default();
            let callback = args.get(2).map(format_value).unwrap_or_default();
            Ok(Some(Value::Int(vm.gui.register_key(object_id as usize, &key, &callback)? as i64)))
        }
        "gui_trykk" => {
            let object_id = read_int(args.first(), "gui_trykk forventer widget-id")?;
            if let Some(callback) = vm.gui.trigger_click(object_id as usize)? {
                invoke_callback(vm, &callback, object_id as usize)?;
            }
            Ok(Some(Value::Int(object_id)))
        }
        "gui_trykk_tast" => {
            let object_id = read_int(args.first(), "gui_trykk_tast forventer widget-id")?;
            let key = args.get(1).map(format_value).unwrap_or_default();
            if let Some(callback) = vm.gui.trigger_key(object_id as usize, &key)? {
                invoke_callback(vm, &callback, object_id as usize)?;
            }
            Ok(Some(Value::Int(object_id)))
        }
        "gui_foresatt" => {
            let object_id = read_int(args.first(), "gui_foresatt forventer widget-id")?;
            Ok(Some(Value::Int(vm.gui.parent_of(object_id as usize)? as i64)))
        }
        "gui_barn" => {
            let parent_id = read_int(args.first(), "gui_barn forventer forelder-id")?;
            let index = read_int(args.get(1), "gui_barn forventer indeks")?;
            Ok(Some(Value::Int(vm.gui.child_at(parent_id as usize, index as usize)? as i64)))
        }
        "gui_sett_tekst" => {
            let object_id = read_int(args.first(), "gui_sett_tekst forventer widget-id")?;
            let text = args.get(1).map(format_value).unwrap_or_default();
            if let Some(callback) = vm.gui.set_text(object_id as usize, &text)? {
                invoke_callback(vm, &callback, object_id as usize)?;
            }
            Ok(Some(Value::Int(object_id)))
        }
        "gui_hent_tekst" => {
            let object_id = read_int(args.first(), "gui_hent_tekst forventer widget-id")?;
            Ok(Some(Value::Text(vm.gui.get_text(object_id as usize)?)))
        }
        "gui_vis" => {
            let object_id = read_int(args.first(), "gui_vis forventer vindu-id")?;
            Ok(Some(Value::Int(vm.gui.show(object_id as usize)? as i64)))
        }
        "gui_lukk" => {
            let object_id = read_int(args.first(), "gui_lukk forventer vindu-id")?;
            Ok(Some(Value::Int(vm.gui.close(object_id as usize)? as i64)))
        }
        _ => Ok(None),
    }
}

fn create_widget<I: Io>(vm: &mut Vm<I>, kind: &str, args: &[Value]) -> Result<Option<Value>, RuntimeError> {
    let parent = GuiState::parent_from_value(args.first())?;
    let text = args.get(1).map(format_value).unwrap_or_default();
    let object_id = vm.gui.create_widget(kind, parent, &text);
    Ok(Some(Value::Int(object_id as i64)))
}

fn read_int(value: Option<&Value>, message: &str) -> Result<i64, RuntimeError> {
    match value {
        Some(Value::Int(n)) => Ok(*n),
        Some(other) => Err(RuntimeError::InvalidOperand(format!("{message}: {other:?}"))),
        None => Err(RuntimeError::InvalidOperand(message.to_string())),
    }
}

fn format_value(value: &Value) -> String {
    match value {
        Value::Int(n) => n.to_string(),
        Value::Bool(true) => "sann".to_string(),
        Value::Bool(false) => "usann".to_string(),
        Value::Text(text) => text.clone(),
        Value::List(items) => items.borrow().iter().map(format_value).collect::<Vec<_>>().join("\n"),
        Value::Null => String::new(),
    }
}

fn invoke_callback<I: Io>(vm: &mut Vm<I>, callback: &str, object_id: usize) -> Result<(), RuntimeError> {
    if let Some(name) = vm.resolve_function_name(callback) {
        let _ = vm.invoke_function(&name, vec![Value::Int(object_id as i64)])?;
    }
    Ok(())
}
